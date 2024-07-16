import h5py
import random
from utils.data.transforms import DataTransform
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
import numpy as np
import time
import torch
from utils.mraugment.data_augment import DataAugmentor
from fastmri.data.subsample import create_mask_for_mask_type
from fastmri.data.transforms import apply_mask

class SliceData(Dataset):
    def __init__(self, root, transform, input_key, target_key, DataAugmentor, args, forward=False):
        self.transform = transform
        self.input_key = input_key
        self.target_key = target_key
        self.forward = forward
        self.image_examples = []
        self.kspace_examples = []
        # MRAugment를 위해 아래 변수들 추가함
        self.DataAugmentor = DataAugmentor
        self.mask_type = args.mask_type
        self.center_fractions = args.center_fractions
        self.accelerations = args.accelerations

        if not forward:
            image_files = list(Path(root / "image").iterdir())

            """
            for fname in sorted(image_files):
                num_slices = self._get_metadata(fname)

                self.image_examples += [
                    (fname, slice_ind) for slice_ind in range(num_slices)
                ]
            """
            # train data의 image_examples는 txt파일에서 가지고 오도록 함
            files_num = len(image_files)
            if files_num==51:
                # val data인 경우 원래처럼 image_examples 가지고 오기
                for fname in sorted(image_files):
                    num_slices = self._get_metadata(fname)

                    # MRaugment를 하는지 안 하는지 세 번째 원소로 표시
                    self.image_examples += [
                        (fname, slice_ind, False) for slice_ind in range(num_slices)
                    ]
                    if DataAugmentor == None: continue
                    self.image_examples += [
                        (fname, slice_ind, True) for slice_ind in range(num_slices)
                    ]
            else:
                self.image_examples = self._get_metadata2('image', DataAugmentor!=None)

        kspace_files = list(Path(root / "kspace").iterdir())

        """
            for fname in sorted(kspace_files):
                num_slices = self._get_metadata(fname)

                self.kspace_examples += [
                    (fname, slice_ind) for slice_ind in range(num_slices)
                ]
            """

        # train data의 kspace_examples는 txt파일에서 가지고 오도록 함
        files_num = len(kspace_files)
        if files_num==51:
            # val data인 경우 원래처럼 kspace_examples 가지고 오기
            for fname in sorted(kspace_files):
                num_slices = self._get_metadata(fname)

                # MRaugment를 하는지 안 하는지 세 번째 원소로 표시
                self.kspace_examples += [
                    (fname, slice_ind, False) for slice_ind in range(num_slices)
                ]
                if DataAugmentor == None: continue
                self.kspace_examples += [
                    (fname, slice_ind, True) for slice_ind in range(num_slices)
                ]
        else:
            self.kspace_examples = self._get_metadata2('kspace', DataAugmentor!=None)


    def _get_metadata(self, fname):
        with h5py.File(fname, "r") as hf:
            if self.input_key in hf.keys():
                num_slices = hf[self.input_key].shape[0]
            elif self.target_key in hf.keys():
                num_slices = hf[self.target_key].shape[0]
        return num_slices

    def _get_metadata2(self, data_type, aug_on):
        examples = []
        if data_type == 'image':
            with open("/content/drive/MyDrive/Data/train_image_examples_mini.txt", "r") as f:
                image_examples = f.read()
                for line in image_examples.split('\n'):
                    fname, dataslice = line.split()
                    # MRaugment를 하는지 안 하는지 세 번째 원소로 표시
                    examples.append(tuple((Path(fname), int(dataslice), False)))
                    if not aug_on: continue
                    examples.append(tuple((Path(fname), int(dataslice), True))) # 튜플의 마지막 원소는 augmentation 할 여부
        elif data_type == 'kspace':
            with open("/content/drive/MyDrive/Data/train_kspace_examples_mini.txt", "r") as f:
                kspace_examples = f.read()
                for line in kspace_examples.split('\n'):
                    fname, dataslice = line.split()
                    # MRaugment를 하는지 안 하는지 세 번째 원소로 표시
                    examples.append(tuple((Path(fname), int(dataslice), False)))
                    if not aug_on: continue
                    examples.append(tuple((Path(fname), int(dataslice), True))) # 튜플의 마지막 원소는 augmentation 할 여부
        return examples

    def __len__(self):
        return len(self.kspace_examples)

    def __getitem__(self, i):
        # image_aug 와 kspace_aug는 augmentation이 필요한지의 여부
        if not self.forward:
            image_fname, _, image_aug = self.image_examples[i]
        kspace_fname, dataslice, kspace_aug = self.kspace_examples[i]
        
        # image_file을 열어서 target_size 가져오기
        with h5py.File(image_fname, "r") as hf:
            target_size = hf[self.target_key][dataslice].shape

        if not kspace_aug:
          with h5py.File(kspace_fname, "r") as hf:
              input = hf[self.input_key][dataslice]
              mask =  np.array(hf["mask"]) # hf파일에 있는 mask.shape은 (396,)
          if self.forward:
              target = -1
              attrs = -1
          else:
              with h5py.File(image_fname, "r") as hf:
                  target = hf[self.target_key][dataslice]
                  attrs = dict(hf.attrs)
        else:
          with h5py.File(kspace_fname, "r") as hf:
              input = hf[self.input_key][dataslice]

              # DataAugmentor에 들어가는 input은 마지막 두 차원이 실수부와 허수부로 나뉘어져 있어야 한다.
              input = torch.from_numpy(input)
              input = torch.stack((input.real, input.imag), dim=-1)

              # augment된 kspace를 input으로 받기 / 그에 대응되는 target도 미리 받아두기
              input, target = self.DataAugmentor(input, [target_size[-2],target_size[-1]]) # input.shape[-1]는 2이다. 실수부와 허수부로 나뉘어져 있다.
              
              # input에 맞는 mask 만들기
              seed = None
              mask_func = create_mask_for_mask_type(self.mask_type, self.center_fractions, self.accelerations)
              _, mask = apply_mask(input, mask_func, seed)
              mask = np.array(torch.squeeze(mask))

              if(input.shape[-1]==2):
                real_part = input[..., 0]
                imaginary_part = input[..., 1]
                complex_tensor = torch.complex(real_part, imaginary_part)
                input = complex_tensor

          if self.forward:
              target = -1
              attrs = -1
          else:
              with h5py.File(image_fname, "r") as hf:
                  # 위에서 만든 augment 적용된 target을 사용
                  # target = hf[self.target_key][dataslice]
                  attrs = dict(hf.attrs)
            
        return self.transform(mask, input, target, attrs, kspace_fname.name, dataslice)


def create_data_loaders(data_path, args, DataAugmentor=None, shuffle=False, isforward=False):
    if isforward == False:
        max_key_ = args.max_key
        target_key_ = args.target_key
    else:
        max_key_ = -1
        target_key_ = -1
    data_storage = SliceData(
        root=data_path,
        transform=DataTransform(isforward, max_key_),
        input_key=args.input_key,
        target_key=target_key_,
        forward = isforward,
        DataAugmentor =  DataAugmentor,
        args = args
    )

    data_loader = DataLoader(
        dataset=data_storage,
        batch_size=args.batch_size,
        shuffle=shuffle,
    )
    return data_loader
