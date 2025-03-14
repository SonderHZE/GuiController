import unittest
import os
from PIL import Image
import numpy as np
from utils import compare_image_similarity

class TestImageSimilarity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 创建测试用临时目录
        cls.test_dir = "tests/test_images"
        os.makedirs(cls.test_dir, exist_ok=True)
        
        # 生成测试图片
        cls.create_test_images()
    
    @classmethod
    def create_test_images(cls):
        # 完全相同图片
        img1 = Image.new('RGB', (100, 100), color=(73, 109, 137))
        cls.identical1 = os.path.join(cls.test_dir, "identical1.png")
        cls.identical2 = os.path.join(cls.test_dir, "identical2.png")
        img1.save(cls.identical1)
        img1.save(cls.identical2)
        
        # 不同尺寸图片
        img2 = Image.new('RGB', (200, 200), color=(73, 109, 137))
        cls.diff_size = os.path.join(cls.test_dir, "diff_size.png")
        img2.save(cls.diff_size)
        
        # 完全不相似图片
        white_img = Image.new('RGB', (100, 100), color=(255, 255, 255))
        black_img = Image.new('RGB', (100, 100), color=(0, 0, 0))
        cls.white_img = os.path.join(cls.test_dir, "white.png")
        cls.black_img = os.path.join(cls.test_dir, "black.png")
        white_img.save(cls.white_img)
        black_img.save(cls.black_img)

    def test_identical_images(self):
        result = compare_image_similarity(self.identical1, self.identical2)
        self.assertAlmostEqual(result["ssim"], 1.0, delta=0.01)
        self.assertEqual(result["mse"], 0)
        self.assertGreater(result["psnr"], 60)

    def test_different_sizes(self):
        result = compare_image_similarity(self.identical1, self.diff_size)
        self.assertGreaterEqual(result["ssim"], 0.8)
        self.assertLess(result["mse"], 100)

    def test_completely_different(self):
        result = compare_image_similarity(self.white_img, self.black_img)
        self.assertAlmostEqual(result["ssim"], -1.0, delta=0.1)
        self.assertGreater(result["mse"], 10000)
        self.assertLess(result["psnr"], 20)

    def test_invalid_path(self):
        result = compare_image_similarity("invalid1.png", "invalid2.png")
        self.assertEqual(result["ssim"], 0.0)
        self.assertEqual(result["mse"], 999999)

if __name__ == '__main__':
    unittest.main()