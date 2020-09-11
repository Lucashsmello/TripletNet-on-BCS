import torch.nn as nn
import torch
import numpy as np
from siamese_triplet.losses import OnlineTripletLoss
from siamese_triplet.trainer import train_epoch
import siamese_triplet.trainer
from .datahandler import BasicTorchDataset
from siamese_triplet.utils import RandomNegativeTripletSelector, HardestNegativeTripletSelector, SemihardNegativeTripletSelector, HardNegativeTripletSelector
from sklearn.base import BaseEstimator, TransformerMixin
from skorch import NeuralNet
from skorch.dataset import uses_placeholder_y
import skorch
from sklearn.cluster import KMeans
from skorch.dataset import unpack_data
from skorch.utils import to_tensor


class EmbeddingNetMNIST(nn.Module):
    def __init__(self, num_outputs):
        super().__init__()
        # input: (1,28,28)
        self.convnet = nn.Sequential(
            nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(),
            nn.MaxPool2d(2, stride=2),
            nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(),
            nn.Flatten()
        )

        self.fc = nn.Sequential(nn.Linear(32*14*14, 256), nn.ReLU(),
                                nn.Linear(256, num_outputs)
                                )

    def forward(self, x):
        x = self.convnet(x)
        x = self.fc(x)

        return x


class NeuralNetTransformer(NeuralNet, TransformerMixin):
    def __init__(self, module, dont_train=False, *args, **kwargs):
        super().__init__(module, *args, **kwargs)
        self.dont_train = dont_train

    def transform(self, X):
        return self.predict(X)

    def fit(self, X, y=None, **fit_params):
        if(self.dont_train):
            return self
        return super().fit(X, y, **fit_params)


class TripletNetwork(NeuralNetTransformer):
    class OnlineTripletLossWrapper(OnlineTripletLoss):
        def __init__(self, margin=1.0, triplet_selector=RandomNegativeTripletSelector(margin=1.0)):
            super().__init__(margin=margin, triplet_selector=triplet_selector)

        def forward(self, net_outputs, target):
            return super().forward(net_outputs, target)[0]

    def __init__(self, module, *args, margin_decay_delay=0, margin_decay_value=0.75, criterion=OnlineTripletLossWrapper, **kwargs):
        super().__init__(module,
                         *args,
                         criterion=criterion,
                         **kwargs)
        self.margin_decay_delay = margin_decay_delay
        self.margin_decay_value = margin_decay_value
        self.epoch_number = 0

    def run_single_epoch(self, dataset, training, prefix, step_fn, **fit_params):
        super().run_single_epoch(dataset, training, prefix, step_fn, **fit_params)
        self.epoch_number += 1
        if(self.margin_decay_delay > 0):
            if(self.epoch_number % self.margin_decay_delay == 0):
                self.criterion_.margin *= self.margin_decay_value

    def get_params(self, deep=True, **kwargs):
        params = super().get_params(deep, **kwargs)
        del params['epoch_number']
        return params

    @staticmethod
    def load(fpath: str, module, **kwargs) -> 'TripletNetwork':
        net = TripletNetwork(module, **kwargs)
        net.initialize()
        net.load_params(fpath)
        return net

    # def load_params(self, f_params=None, f_optimizer=None, f_history=None,
    #                 checkpoint=None):
    #     def _get_state_dict(f):
    #         map_location = skorch.utils.get_map_location(self.device)
    #         self.device = self._check_device(self.device, map_location)
    #         return torch.load(f, map_location=map_location)

    #     if f_params is not None:
    #         msg = (
    #             "Cannot load parameters of an un-initialized model. "
    #             "Please initialize first by calling .initialize() "
    #             "or by fitting the model with .fit(...).")
    #         self.check_is_fitted(msg=msg)
    #         state_dict = _get_state_dict(f_params)['state_dict']
    #         self.module_.load_state_dict(state_dict)
    #     super().load_params(None, f_optimizer, f_history, checkpoint)


class TripletEnsembleNetwork(TripletNetwork):
    class SubDataset(torch.utils.data.Subset):
        def __init__(self, dataset, line_idxs):
            super().__init__(dataset, line_idxs)
            if(hasattr(dataset, 'y')):
                self.targets = dataset.y
            else:
                self.targets = dataset.targets
            self.targets = self.targets[line_idxs]

    def __init__(self, module, k=2, *args, criterion=TripletNetwork.OnlineTripletLossWrapper, **kwargs):
        super().__init__(module,
                         *args,
                         criterion=criterion,
                         **kwargs)
        self.k = k

    def run_single_epoch(self, dataset, training, prefix, step_fn, **fit_params):
        is_placeholder_y = uses_placeholder_y(dataset)

        X, Y = [], []

        for data in self.get_iterator(dataset, training=training):
            Xi, yi = unpack_data(data)
            yi_res = yi if not is_placeholder_y else None
            with torch.no_grad():
                X.append(self.transform(Xi))
            Y.append(yi)

        X = np.concatenate(X)
        Y = np.concatenate(Y)

        kmeans = KMeans(n_clusters=self.k).fit(X)
        idxs = [np.where(kmeans.labels_ == i)[0] for i in range(self.k)]
        m = X.shape[-1]//self.k
        for i, idx in enumerate(idxs):
            if(len(idx) < 3):
                continue
            self.feats_idxs = list(range(i*m, (i+1)*m))
            subdataset = TripletEnsembleNetwork.SubDataset(dataset, idx)
            try:
                super().run_single_epoch(subdataset, training, prefix, step_fn, **fit_params)
            except:
                import sys
                print("Unexpected error:", sys.exc_info()[0])

    def get_loss(self, y_pred, y_true, X=None, training=False):
        y_true = to_tensor(y_true, device=self.device)
        return self.criterion_(y_pred[:, self.feats_idxs], y_true)

    @staticmethod
    def load(fpath: str, module, **kwargs) -> 'TripletEnsembleNetwork':
        net = TripletEnsembleNetwork(module, k=0, **kwargs)
        net.initialize()
        net.load_params(fpath)
        return net


class lmelloEmbeddingNet(nn.Module):
    def __init__(self, num_outputs, num_inputs_channels=1):
        super().__init__()
        self.convnet = nn.Sequential(
            nn.Conv1d(num_inputs_channels, 16, 5), nn.LeakyReLU(negative_slope=0.05),
            nn.Dropout(p=0.2),
            nn.MaxPool1d(4, stride=4),
            nn.Conv1d(16, 32, 5), nn.LeakyReLU(negative_slope=0.05),
            nn.Dropout(p=0.2),
            nn.MaxPool1d(4, stride=4),
            nn.Conv1d(32, 64, 5), nn.LeakyReLU(negative_slope=0.05),
            nn.Dropout(p=0.2),
            nn.MaxPool1d(4, stride=4),
            nn.Flatten()
        )

        self.fc = nn.Sequential(nn.Linear(64 * 94, 192),
                                nn.LeakyReLU(negative_slope=0.05),
                                nn.Linear(192, num_outputs)
                                )

    def forward(self, x):
        output = self.convnet(x)
        output = self.fc(output)
        return output

    def encode(self, x):
        with torch.no_grad():
            if(len(x.shape) == 1):
                n = 1
                x = torch.tensor(x[:6100], dtype=torch.float32).cuda()
                x = x.reshape((1, 1, 6100))
                return self.forward(x).squeeze()
            else:
                n = x.shape[0]
                ret = torch.empty((n, self.num_outputs), dtype=torch.float32).cuda()
                k = 0
                for i in range(0, n, 8):
                    batch = torch.tensor(x[i:i+8, :6100], dtype=torch.float32).cuda()
                    batch = batch.reshape(batch.shape[0], 1, 6100)
                    output = self.forward(batch).squeeze()
                    ret[k:k+len(output)] = output
                    k += len(output)
                return ret

            # if(next(self.parameters()).is_cuda):
            #     x = x.cuda()


class lmelloEmbeddingNet2(lmelloEmbeddingNet):
    def __init__(self, num_outputs, num_inputs_channels=1):
        super().__init__(num_outputs, num_inputs_channels)
        self.convnet = nn.Sequential(
            nn.Conv1d(num_inputs_channels, 16, 5), nn.ReLU(),
            nn.MaxPool1d(4, stride=4),
            nn.Conv1d(16, 32, 5), nn.ReLU(),
            nn.MaxPool1d(4, stride=4),
            nn.Conv1d(32, 64, 5), nn.ReLU(),
            nn.MaxPool1d(4, stride=4),
            nn.Flatten()
        )

        self.fc = nn.Sequential(nn.Linear(64 * 94, 192),
                                nn.ReLU(),
                                nn.Linear(192, num_outputs)
                                )

    def forward(self, x):
        output = self.convnet(x)
        output = self.fc(output)
        return output

    def get_embedding(self, x):
        return self.forward(x)


def extract_embeddings(dataloader, model, num_outputs=-1, use_cuda=True, with_labels=True):
    if(num_outputs <= 0):
        for last_module in model.modules():
            pass
        num_outputs = last_module.out_features
    with torch.no_grad():
        model.eval()
        embeddings = np.zeros((len(dataloader.dataset), num_outputs))
        if(with_labels):
            labels = np.zeros(len(dataloader.dataset))
        k = 0
        for samples, target in dataloader:
            if use_cuda:
                samples = samples.cuda()
            embeddings[k:k+len(samples)] = model.forward(samples).data.cpu().numpy()
            if(with_labels):
                labels[k:k+len(samples)] = target.numpy()
            k += len(samples)
    if(with_labels):
        return embeddings, labels
    return embeddings
########################

# from torchsummary import summary

# net=lmelloEmbeddingNet(8)
# net.cuda()
# summary(net, input_size=(1, 6100))
