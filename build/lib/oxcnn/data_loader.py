import random
import os
import json
import numpy as np
from oxcnn.volume_handler import ImageHandler
from oxcnn.deepmedic_config_reader import DeepMedicConfigReader
import nibabel as nib
from skimage.measure import block_reduce
from skimage.exposure import rescale_intensity

class AbstractDataLoader(object):
    def read_metadata(self, filename):
        with open(filename,'r') as f:
            d = json.load(f)
        self.train_tups = d['train_tups']
        self.validation_tups = d['validation_tups']
        self.test_tups = d['test_tups']

    def read_deepmedic_dir(self,deep_medic_dir):
        dm_cfg_reader = DeepMedicConfigReader(deep_medic_dir)
        self.train_tups = dm_cfg_reader.read_train_tups()
        self.validation_tups = dm_cfg_reader.read_validation_tups()
        self.test_tups = dm_cfg_reader.read_test_tups()

    def read_data_dir(self,data_dir,ttv_list):
        tups = []
        for d in os.listdir(data_dir):
            f = [os.path.join(data_dir,d,x) for x in os.listdir(os.path.join(data_dir,d)) if 'mask' not in x and 'thresh' not in x and 'distmap' not in x and os.path.isfile(os.path.join(data_dir,d,x))][0]
            m = [os.path.join(data_dir,d,x) for x in os.listdir(os.path.join(data_dir,d)) if 'mask' in x and 'thresh' not in x][0]
            s = [os.path.join(data_dir,d,x) for x in os.listdir(os.path.join(data_dir,d)) if 'mask' not in x and 'thresh' in x][0]
            tups.append((f,m,s))
        random.shuffle(tups)
        self.train_tups = tups[0:ttv_list[0]]
        self.validation_tups = tups[ttv_list[0]:ttv_list[0]+ttv_list[1]]
        self.test_tups = tups[ttv_list[0]+ttv_list[1]:ttv_list[0]+ttv_list[1]+ttv_list[2]]

    def get_batch(self,tup):
        raise NotImplementedError( "Should have implemented get_batch" )

    def vol_s(self, tup):
        raise NotImplementedError( "Should have implemented vol_s" )

    def exclude_windows_outside_mask(self,mask_arr,*vol_segs):
        mins_inds = lambda inds: np.array([ x.min() for x in  inds])
        maxs_inds = lambda inds: np.array([ x.max() for x in  inds])+1
        indices = lambda inds: tuple([slice(m1,m2) for m1,m2 in zip(mins_inds(inds),maxs_inds(inds))])
        my_list_tups = [vs for vs in zip(*vol_segs) if np.any(mask_arr[indices(vs[1].inds)])]
        return list(zip(*my_list_tups)) 

class StandardDataLoader(AbstractDataLoader):
    def __init__(self, stride=None, segment_size=None, crop_by=0, rnd_offset=None, aug_pos_samps=False):
        self.stride = stride
        self.segment_size = segment_size
        self.crop_by = crop_by
        self.rnd_offset = rnd_offset
        self.aug_pos_samps = aug_pos_samps

    def get_batch(self, tup, equal_class_size=True):
        print('Reading img {}'.format(tup[0]))
        batchx = []
        batchy = []
        vimgs, vsegs = self.vol_s(tup,self.crop_by)
        pos_samps = [(v.seg_arr, vseg.seg_arr) for v, vseg
                     in zip(vimgs, vsegs) if np.any(vseg.seg_arr)]
        if self.aug_pos_samps: 
            pos_samps = pos_samps + [(np.fliplr(v1),np.fliplr(v2)) for v1,v2 in pos_samps] #+ [(np.rot90(v1),np.rot90(v2)) for v1,v2 in pos_samps] #+ [(np.flipud(v1),np.flipud(v2)) for v1,v2 in pos_samps] 
        neg_samp_list = [(v.seg_arr, vseg.seg_arr) for v, vseg
                         in zip(vimgs, vsegs) if not np.any(vseg.seg_arr)]
        pos_vs, pos_vseg = list(zip(*pos_samps)) 
        #print(len(neg_samp_list), len(pos_samps))
        neg_samps = random.sample(neg_samp_list, min(len(neg_samp_list),len(pos_samps))) if equal_class_size else neg_samp_list
        neg_vs, neg_vseg = [x[0] for x in neg_samps], [x[1] for x in neg_samps]
        batchx += pos_vs
        batchy += pos_vseg
        batchx += neg_vs
        batchy += neg_vseg
        print('Done reading img {} with number of segments {} of size {} MBs'.format(tup[0],len(batchx),(sum([x.nbytes for x in batchx]) + sum([x.nbytes for x in batchy]) )/10**6))
        return np.array(batchx), np.array(batchy), (len(pos_vs), len(neg_vs))

    def vol_s(self, tup, crop_by=0):
        img_file_path, mask_file_path, seg_file_path = tup
        img_handler = ImageHandler()
        image_arr =  nib.load(img_file_path).get_data()
        mask_arr =  nib.load(mask_file_path).get_data()
        seg_arr =  nib.load(seg_file_path).get_data().astype(np.uint8)
        image_arr = mask_arr*image_arr + (1-mask_arr)*(image_arr.max())
        vol_list = img_handler.image_to_vols(image_arr, self.stride, self.segment_size, crop_by=crop_by, rnd_offset=self.rnd_offset, mask_arr=mask_arr)
        tuples = [(np.array(vol.seg_arr.shape)-2*crop_by,vol.start_voxel+crop_by) for vol in vol_list]
        vol_list_segs = img_handler.image_vols_to_vols(seg_arr, tuples)
        return self.exclude_windows_outside_mask(mask_arr, vol_list, vol_list_segs)

class StandardDataLoaderDistMap(AbstractDataLoader):
    def __init__(self, stride, segment_size, crop_by=0, rnd_offset=None):
        self.stride = stride
        self.segment_size = segment_size
        self.crop_by = crop_by

    def read_data_dir(self,data_dir,ttv_list):
        tups = []
        for d in os.listdir(data_dir):
            f = [os.path.join(data_dir,d,x) for x in os.listdir(os.path.join(data_dir,d)) if 'mask' not in x and 'thresh' not in x and 'distmap' not in x][0]
            m = [os.path.join(data_dir,d,x) for x in os.listdir(os.path.join(data_dir,d)) if 'mask' in x and 'thresh' not in x][0]
            s = [os.path.join(data_dir,d,x) for x in os.listdir(os.path.join(data_dir,d)) if 'mask' not in x and 'thresh' in x][0]
            dm = [os.path.join(data_dir,d,x) for x in os.listdir(os.path.join(data_dir,d)) if 'distmap' in x][0]
            tups.append((f, m, s, dm))
        random.shuffle(tups)
        self.train_tups = tups[0:ttv_list[0]]
        self.validation_tups = tups[ttv_list[0]:ttv_list[0]+ttv_list[1]]
        self.test_tups = tups[ttv_list[0]+ttv_list[1]:ttv_list[0]+ttv_list[1]+ttv_list[2]]

    def read_deepmedic_dir(self,deep_medic_dir):
        super().read_deepmedic_dir(deep_medic_dir)
        def append_to_tups(tups):
            new_tups = []
            for tup in tups:
                dname = os.path.dirname(tup[0])
                dm = [os.path.join(dname,x) for x in os.listdir(os.path.join(dname)) if 'distmap' not in x][0]
                new_tups.append( tup + (dm,) )
            return new_tups
        self.train_tups = append_to_tups(self.train_tups)
        self.validation_tups = append_to_tups(self.validation_tups)
        self.test_tups = append_to_tups(self.test_tups)
        print(self.train_tups)

    def get_batch(self, tup):
        print('Reading img {}'.format(tup[0]))
        batchx = []
        batchy = []
        batchy_dm = []
        vimgs, vsegs, vdms = self.vol_s(tup,self.crop_by)
        pos_samps = [(v.seg_arr, vseg.seg_arr, vdm.seg_arr) for v, vseg, vdm
                     in zip(vimgs, vsegs, vdms) if np.any(vseg.seg_arr)]
        neg_samp_list = [(v.seg_arr, vseg.seg_arr, vdm.seg_arr) for v, vseg, vdm
                         in zip(vimgs, vsegs, vdms) if not np.any(vseg.seg_arr)]
        pos_vs, pos_vseg, pos_vdm = list(zip(*pos_samps))
        neg_samps = random.sample(neg_samp_list, min(len(neg_samp_list),len(pos_samps)))
        neg_vs, neg_vseg, neg_vdm = list(zip(*neg_samps))
        batchx += pos_vs
        batchx += neg_vs
        batchy += pos_vseg
        batchy += neg_vseg
        batchy_dm += pos_vdm
        batchy_dm += neg_vdm
        print('Done reading img {} with number of segments {} of size {} MBs'.format(tup[0],len(batchx),(sum([x.nbytes for x in batchx]) + sum([x.nbytes for x in batchy]) )/10**6))
        return np.array(batchx), np.array(batchy), np.array(batchy_dm)

    def vol_s(self, tup, crop_by=0):
        img_file_path, mask_file_path, seg_file_path, dm_file_path = tup
        img_handler = ImageHandler()
        image_arr =  nib.load(img_file_path).get_data()
        mask_arr =  nib.load(mask_file_path).get_data()
        seg_arr =  nib.load(seg_file_path).get_data().astype(np.uint8)
        dm_arr =  nib.load(seg_file_path).get_data().astype(np.float32)
        dm_arr = rescale_intensity(dm_arr, in_range='image', out_range=(0,1))
        image_arr = mask_arr*image_arr + (1-mask_arr)*(image_arr.max())
        vol_list = img_handler.image_to_vols(image_arr, self.stride, self.segment_size, crop_by=crop_by, add_rnd_offset=False)
        tuples = [(np.array(vol.seg_arr.shape)-2*crop_by,vol.start_voxel+crop_by) for vol in vol_list]
        vol_list_segs = img_handler.image_vols_to_vols(seg_arr, tuples)
        vol_list_dms = img_handler.image_vols_to_vols(seg_arr, tuples)
        return self.exclude_windows_outside_mask(mask_arr, vol_list, vol_list_segs, vol_list_dms)

class TwoPathwayDataLoader(AbstractDataLoader):
    def __init__(self, stride, segment_size, segment_size_ss, ss_factor=3, crop_by=0):
        self.stride = stride
        self.segment_size = segment_size
        self.segment_size_ss = segment_size_ss
        self.crop_by = crop_by
        self.ss_factor = ss_factor

    def get_batch(self,tup):
        print('Reading img {}'.format(tup[0]))
        batchx = []
        batchx_ss = []
        batchy = []
        vimgs, vsegs, vimgs_subsampleds = self.vol_s(tup, self.crop_by)
        pos_samps = [(v.seg_arr, vseg.seg_arr, v_ss.seg_arr) for v, vseg, v_ss,
                         in zip(vimgs, vsegs, vimgs_subsampleds) if np.any(vseg.seg_arr)]
        pos_vs, pos_vseg, pos_vs_subsampleds  = zip(*pos_samps)
        neg_samp_list = [(v.seg_arr, vseg.seg_arr, v_ss.seg_arr) for v, vseg, v_ss
                         in zip(vimgs, vsegs, vimgs_subsampleds) if not  np.any(vseg.seg_arr)]
        neg_samps = random.sample(neg_samp_list, min(len(neg_samp_list),len(pos_samps)))
        neg_vs, neg_vseg, neg_vs_subsampleds = zip(*neg_samps)
        batchx += pos_vs
        batchx_ss += pos_vs_subsampleds
        batchy += pos_vseg
        batchx += neg_vs
        batchx_ss += neg_vs_subsampleds
        batchy += neg_vseg
        print('Done reading img {} with number of segments {} of size {} MBs'.format(tup[0],len(batchx),(sum([x.nbytes for x in batchx]) + sum([x.nbytes for x in batchy]) + sum([x.nbytes for x in batchx_ss]) )/10**6))
        return np.array(batchx), np.array(batchy), np.array(batchx_ss), (len(pos_vs), len(neg_vs))


    def vol_s(self, tup, crop_by = 0):
        img_file_path, mask_file_path, seg_file_path = tup
        img_handler = ImageHandler()
        image_arr = nib.load(img_file_path).get_data()
        mask_arr = nib.load(mask_file_path).get_data()
        block_image_arr = block_reduce(image_arr,block_size=(3,3,3),func=np.median).astype(np.uint8)
        vol_list = img_handler.image_to_vols(image_arr, self.stride, self.segment_size, crop_by=crop_by)
        tuples = [(np.array(vol.seg_arr.shape) - 2*crop_by, vol.start_voxel + crop_by) for vol in vol_list]
        seg_arr =  nib.load(seg_file_path).get_data().astype(np.uint8)
        vol_list_segs = img_handler.image_vols_to_vols(seg_arr, tuples)
        tuples = [(self.segment_size_ss, ((vol.start_voxel + (self.segment_size-self.ss_factor*self.segment_size_ss)//2)//self.ss_factor)) for vol in vol_list]
        vol_list_subsampled = img_handler.image_vols_to_vols(block_image_arr, tuples)
        return self.exclude_windows_outside_mask(mask_arr, vol_list, vol_list_segs, vol_list_subsampled)
