import numpy as np
import sys
import nibabel as nib
import tempfile
from oxcnn.test import utils
from oxcnn.volume_handler import VolumeSegment, ImageHandler
from oxcnn.data_loader import TwoPathwayDataLoader
import matplotlib.pyplot as plt
import unittest
from skimage.measure import block_reduce

def main():
    in_dir = sys.argv[1]
    vol_list = img_handler.image_to_vols(image_arr,stride,window_shape,add_rnd_offset=False)

if __name__=='__main__':
    main()
