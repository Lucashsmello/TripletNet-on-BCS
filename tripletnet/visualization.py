import matplotlib.pyplot as plt
import numpy as np
from mpl_toolkits.mplot3d import Axes3D
import seaborn as sns
import pandas as pd


_COLORS = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
           '#9467bd', '#8c564b', '#e377c2', '#7f7f7f',
           '#bcbd22', '#17becf']


def pairplot_embeddings(embeddings, targets, classes=None, show=True):
    data = {'f%d' % (i+1): embeddings[:, i] for i in range(embeddings.shape[1])}
    df = pd.DataFrame(data)
    if(classes is None):
        df['class'] = ["c"+str(t) for t in targets]
        mypalette = {"c"+str(t): _COLORS[t] for t in list(set(targets))}
    else:
        df['class'] = [classes[t][0] for t in targets]
        mypalette = {classes[c][0]: classes[c][1] for c in classes}
    sns.pairplot(df, hue="class", diag_kind='kde', kind='scatter',
                 palette=mypalette, plot_kws={'alpha': 0.5})
    # sns.pairplot(df, hue="class", diag_kind='hist', kind='scatter',
    #            palette=mypalette, plot_kws={'alpha': 0.5})
    #plt.savefig('%d_extracted.png' % embeddings.shape[0])
    if(show):
        plt.show()


def plot_embeddings(embeddings, targets, classes, xlim=None, ylim=None):
    plt.figure(figsize=(10, 10))
    class_set = set(targets)
    for i in class_set:
        i = int(i)
        inds = np.where(targets == i)[0]
        if(len(inds) > 0):
            c = classes[i]
            if(isinstance(c, str)):
                plt.scatter(embeddings[inds, 0], embeddings[inds, 1],
                            alpha=0.5, color=_COLORS[i], label=c)
            else:
                plt.scatter(embeddings[inds, 0], embeddings[inds, 1],
                            alpha=0.5, color=c[1], label=c[0])

    if xlim:
        plt.xlim(xlim[0], xlim[1])
    if ylim:
        plt.ylim(ylim[0], ylim[1])
    plt.legend()
    plt.show()


def plot_embeddings3d(embeddings, targets, classes, xlim=None, ylim=None):
    fig = plt.figure()
    ax = Axes3D(fig)
    class_set = set(targets)
    for i in class_set:
        i = int(i)
        inds = np.where(targets == i)[0]
        if(len(inds) > 0):
            c = classes[i]
            if(isinstance(c, str)):
                ax.scatter(embeddings[inds, 0], embeddings[inds, 1], embeddings[inds, 2],
                           alpha=0.5, color=_COLORS[i], label=c)
            else:
                ax.scatter(embeddings[inds, 0], embeddings[inds, 1], embeddings[inds, 2],
                           alpha=0.5, color=c[1], label=c[0])
    if xlim:
        plt.xlim(xlim[0], xlim[1])
    if ylim:
        plt.ylim(ylim[0], ylim[1])
    plt.legend()
    plt.show()
