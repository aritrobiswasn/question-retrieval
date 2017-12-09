import argparse
import torch
from torch import nn
from torch.nn.modules.loss import _Loss
import torch.nn.functional as F
from torch.utils.data import DataLoader
from dataloader import UbuntuDataset, batchify, create_variable
from lstm_model import LSTMRetrieval
from cnn_model import CNN
import numpy as np
from collections import defaultdict
from domain_classifier import DomainClassifier
from main import MaxMarginCosineSimilarityLoss, get_moving_average

from itertools import repeat, cycle, islice, izip
def roundrobin(*iterables):
    "roundrobin('ABC', 'D', 'EF') --> A D E B F C"
    # Recipe credited to George Sakkis
    pending = len(iterables)
    nexts = cycle(iter(it).next for it in iterables)
    while pending:
        try:
            for next in nexts:
                yield next()
        except StopIteration:
            pending -= 1
            nexts = cycle(islice(nexts, pending))

def run_epoch(
    args, ubuntu_loader, android_loader, qr_model, qr_criterion, qr_optimizer,
    dc_model, dc_criterion, dc_optimizer, epoch, mode='train'
    ):
    queries_per_batch = args.batch_size/args.examples_per_query

    if mode == 'train':
        print "Training..."
    elif mode == 'val':
        print "Validation..."

    data_and_target_loaders = [ izip(ubuntu_loader , repeat(0)), 
                                izip(android_loader, repeat(1)) ]
    data_and_target_loader = roundrobin(*data_and_target_loaders)

    print "Epoch {}".format(epoch)
    queries_count = 0 # Queries seen so far in this epoch.
    qr_total_loss = 0
    dc_total_loss = 0

    for i_batch, (data, target_domain) in enumerate(data_and_target_loader):
        _, padded_things, ys = data

        print "Batch #{}, Domain {}".format(i_batch, target_domain)
        ys = create_variable(ys)

        qt, qb, ot, ob = padded_things # padded_things might also be packed.
        # qt is (PackedSequence, perm_idx), or (seq_tensor, set_lengths)

        # Step 1. Remember that Pytorch accumulates gradients. 
        # We need to clear them out before each instance
        for model in [qr_model, dc_model]:
            model.zero_grad()
        
        # Generate embeddings.
        query_title = qr_model.get_embed(*qt)
        query_body = qr_model.get_embed(*qb)
        other_title = qr_model.get_embed(*ot)
        other_body = qr_model.get_embed(*ob)

        query_embed = (query_title + query_body) / 2
        other_embed = (other_title + other_body) / 2

        # Classify their domains
        query_domain, other_domain = dc_model(query_embed), dc_model(other_embed)

        # Compute batch loss
        target = create_variable(torch.FloatTensor([float(target_domain)]*args.batch_size))

        qr_batch_loss = qr_criterion(query_embed, other_embed, ys)
        qr_total_loss += qr_batch_loss.data[0]
        print "avg QR loss for batch {} was {}".format(i_batch, qr_batch_loss.data[0]/queries_per_batch)

        dc_batch_loss = sum(dc_criterion(predicted_domain, target) 
                            for predicted_domain in [query_domain, other_domain])
        dc_total_loss += dc_batch_loss.data[0]
        print "avg DC loss for batch {} was {}".format(i_batch, dc_batch_loss.data[0]/queries_per_batch)
        
        if mode == 'train':
            if target_domain == 0: # ubuntu. We don't have android training data for QR.
                qr_batch_loss.backward(retain_graph=True)
                qr_optimizer.step()
            else:
                pass # android. 
            dc_batch_loss.backward()
            dc_optimizer.step()
    qr_avg_loss = qr_total_loss / queries_count
    dc_avg_loss = dc_total_loss / queries_count
    print "average {} QR loss for epoch {} was {}".format(mode, epoch, qr_avg_loss)
    print "average {} DC loss for epoch {} was {}".format(mode, epoch, dc_avg_loss)

def main(args):
    load, save, train, evaluate = args.load, args.save, not args.no_train, not args.no_evaluate
    del args.load
    del args.save
    del args.no_train
    del args.no_evaluate

    print "Initializing Ubuntu Dataset..."
    ubuntu_train_loader = DataLoader(
        UbuntuDataset(name='ubuntu', partition='train'),
        batch_size=args.batch_size, # 20*n -> n questions.
        shuffle=False,
        num_workers=8,
        collate_fn=batchify
    )
    ubuntu_val_loader = DataLoader(
        UbuntuDataset(name='ubuntu', partition='dev'),
        batch_size=args.batch_size, # 20*n -> n questions.
        shuffle=False,
        num_workers=8,
        collate_fn=batchify
    )

    print "Initializing Android Dataset..."
    # Note, Android train data isn't labeled.
    android_train_loader = DataLoader(
        UbuntuDataset(name='android', partition='dev'), # TODO use train when it becomes availlable
        batch_size=args.batch_size, # 20*n -> n questions.
        shuffle=False,
        num_workers=8,
        collate_fn=batchify
    )
    android_val_loader = DataLoader(
        UbuntuDataset(name='android', partition='dev'),
        batch_size=args.batch_size, # 20*n -> n questions.
        shuffle=False,
        num_workers=8,
        collate_fn=batchify
    )

    # MODELS

    dc_model = DomainClassifier(args.hidden_size)

    if args.model_type == 'lstm':
        print "----LSTM----"
        qr_model = LSTMRetrieval(args.input_size, args.hidden_size, args.num_layers, args.pool, batch_size=args.batch_size)
    elif args.model_type == 'cnn':
        print "----CNN----"
        qr_model = CNN(args.input_size, args.hidden_size, args.pool, batch_size=args.batch_size)
    else: 
        raise RuntimeError('Unknown --model_type')

    # CUDA

    if torch.cuda.is_available():
        print "Using CUDA"
        for model in [dc_model, qr_model]:
            model = model.cuda()
            model.share_memory()

    # Loss functions and Optimizers
    dc_criterion = nn.L1Loss() # TODO: Replace with actual.
    dc_optimizer = torch.optim.SGD(dc_model.parameters(), lr=args.dc_lr)

    qr_criterion = MaxMarginCosineSimilarityLoss() # TODO...
    qr_optimizer = torch.optim.SGD(qr_model.parameters(), lr=args.qr_lr)

    for epoch in xrange(args.epochs):
        if train:
            run_epoch(
                args, ubuntu_train_loader, android_train_loader, qr_model, qr_criterion, 
                qr_optimizer, dc_model, dc_criterion, dc_optimizer, epoch, 
                mode='train'
            )
        if evaluate:
            if epoch % args.val_epoch == 0:
                run_epoch(
                    args, ubuntu_val_loader, android_val_loader, qr_model, qr_criterion, 
                    qr_optimizer, dc_model, dc_criterion, dc_optimizer, epoch, 
                    mode='val'
                )

if __name__=="__main__":
    parser = argparse.ArgumentParser()

    # loading and saving models. 'store_true' flags default to False. 
    parser.add_argument('--load', action='store_true')
    parser.add_argument('--save', action='store_true')
    parser.add_argument('--no-train', action='store_true')
    parser.add_argument('--no-evaluate', action='store_true')

    # model parameters
    parser.add_argument('--model_type', default='lstm', type=str, choices=['lstm', 'cnn'])
    parser.add_argument('--hidden_size', default=200, type=int)
    parser.add_argument('--input_size', default=200, type=int)
    parser.add_argument('--num_layers', default=3, type=int)
    parser.add_argument('--pool', default='max', type=str, choices=['max', 'avg'])

    # training parameters
    parser.add_argument('--batch_size', default=80, type=int) # constraint: batch_size must be a multiple of other_questions_size
    parser.add_argument('--examples_per_query', default=20, type=int) # the number of other questions that we want to have for each query
    parser.add_argument('--epochs', default=2, type=int)
    parser.add_argument('--dc_lr', default=0.005, type=float)
    parser.add_argument('--qr_lr', default=0.005, type=float)

    # miscellaneous
    parser.add_argument('--val_epoch', default=1, type=int)
    parser.add_argument('--stats_display_interval', default=1, type=int)

    args = parser.parse_args()
    main(args)
