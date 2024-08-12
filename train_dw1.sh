python train_no_wandb.py \
  -b 1 \
  -a 4 \
  -e 15 \
  -l 0.001 \
  -p 5 \
  -f 0.1 \
  -m 1.0 \
  -r 50 \
  -i 100 \
  -n 'ensemble-test' \
  -t '/content/drive/MyDrive/Data/val' \
  -v '/content/drive/MyDrive/Data/val' \
  --cascade 3 \
  --chans 12 \
  --sens_chans 5 \
  --unet_chans 5 \
  --input-key 'kspace' \
  --target-key 'image_label' \
  --max-key 'max' \
  --seed 430
