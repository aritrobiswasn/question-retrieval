# nlp-final-project

Online stack exchange forums provide a large source of question and answer pairs. We leverage this data towards the task of question retrieval, i.e. to retrieve questions similar to query questions, and give higher scores to more similar questions. Such a system has practical value; for instance, a user wanting to ask a question might use this system to find a similar question that has already been answered. However, this task is also interesting from a natural language perspective. Constructing a good representation from the question body for this task is challenging, as in many instances, the body content might have lots of information specific to the user and not directly relevant to the question, making it challenging to filter out the relevant information.

We studied the problem of question retrieval in 2 settings. In the first setting, we are interested in the question retrieval task when trained on evaluated on the Ubuntu Stack Exchange Dataset. In the second setting, we are interested in using domain adaptation techniques to transfer a model trained off of labeled data from Ubuntu Stack Exchange and unlabeled data from Android Stack Exchange, and evaluating it on Android Stack Exchange.

One of our models is Long Short Term Memory (LSTM) network, and the other is a Convolutional Neural Network (CNN). Then, we explored the possibility of using transfer learning to solve a similar Question Retrieval task on the Stack Exchange Android dataset. We establish direct transfer as a baseline, and show that Domain Adaptation can be used to outperform that baseline.

For a more in-depth discussion of our results, please look at project_writeup.pdf

December 2017

References:
Unsupervised Domain Adaptation by Backpropagation. Ganin, Y.; Lempitsky, V.
