from options.train_options import TrainOptions
from models.networks import ResUnetGenerator, load_checkpoint_parallel
import torch.nn as nn
import os
import numpy as np
import torch
from torch.utils.data import DataLoader
import cv2
from tqdm import tqdm

opt = TrainOptions().parse()
os.makedirs('sample/'+opt.name, exist_ok=True)

def CreateDataset(opt):
    if opt.dataset == 'vitonhd':
        from data.aligned_dataset_vitonhd import AlignedDataset
        dataset = AlignedDataset()
        dataset.initialize(opt, mode='test')
    elif opt.dataset == 'dresscode':
        from data.aligned_dataset_dresscode import AlignedDataset
        dataset = AlignedDataset()
        dataset.initialize(opt, mode='test', stage='gen')
    return dataset

device = torch.device('cuda')

train_data = CreateDataset(opt)
train_loader = DataLoader(train_data, batch_size=opt.batchSize, shuffle=False,
                          num_workers=2, pin_memory=True)

gen_model = ResUnetGenerator(36, 4, 5, ngf=64, norm_layer=nn.BatchNorm2d)
gen_model.train()
gen_model.cuda()
load_checkpoint_parallel(gen_model, opt.PBAFN_gen_checkpoint)

model_gen = gen_model
model_gen.eval()

for data in tqdm(train_loader):
    real_image = data['image'].cuda()
    clothes = data['color'].cuda()
    preserve_mask = data['preserve_mask3'].cuda()
    preserve_region = real_image * preserve_mask
    warped_cloth = data['warped_cloth'].cuda()
    warped_prod_edge = data['warped_edge'].cuda()
    arms_color = data['arms_color'].cuda()
    arms_neck_label= data['arms_neck_lable'].cuda()
    pose = data['pose'].cuda()

    gen_inputs = torch.cat([preserve_region, warped_cloth, warped_prod_edge, arms_neck_label, arms_color, pose], 1)

    gen_outputs = model_gen(gen_inputs)
    p_rendered, m_composite = torch.split(gen_outputs, [3, 1], 1)
    p_rendered = torch.tanh(p_rendered)
    m_composite = torch.sigmoid(m_composite)
    m_composite = m_composite * warped_prod_edge
    p_tryon = warped_cloth * m_composite + p_rendered * (1 - m_composite)
    k = p_tryon

    bz = pose.size(0)
    for bb in range(bz):
        combine = k[bb].squeeze()
    
        cv_img = (combine.permute(1, 2, 0).detach().cpu().numpy()+1)/2
        rgb = (cv_img*255).astype(np.uint8)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)

        cloth_id = data['color_path'][bb].split('/')[-1]
        person_id = data['img_path'][bb].split('/')[-1]
        c_type = data['c_type'][bb]
        save_path = 'sample/'+opt.name+'/'+c_type+'___'+person_id+'___'+cloth_id[:-4]+'.png'
        cv2.imwrite(save_path, bgr)
