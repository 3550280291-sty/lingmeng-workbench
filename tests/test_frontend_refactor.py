# -*- coding: utf-8 -*-
import unittest
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app", "web")

class TestFrontendRefactor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP_DIR, "index.html"), "r", encoding="utf-8") as f:
            cls.html = f.read()
        with open(os.path.join(APP_DIR, "style.css"), "r", encoding="utf-8") as f:
            cls.css = f.read()
        with open(os.path.join(APP_DIR, "app.js"), "r", encoding="utf-8") as f:
            cls.js = f.read()

    def test_core_1_toggle_btn_and_typography(self):
        # 成果舱与文件按钮样式
        self.assertIn("toggle-panel-btn", self.html)
        self.assertIn(".toggle-panel-btn", self.css)
        self.assertIn("white-space: nowrap !important;", self.css)
        self.assertIn("width: auto !important;", self.css)
        self.assertIn("flex-direction: row !important;", self.css)

        # macOS/iOS 字体体系
        self.assertIn('-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;', self.css)

        # 卡片 min-width 与 2 行截断
        self.assertIn("min-width: 160px !important;", self.css)
        self.assertIn("-webkit-line-clamp: 2 !important;", self.css)
        self.assertIn("-webkit-box-orient: vertical !important;", self.css)

    def test_core_2_sidebar_history_and_dom(self):
        # 侧边栏列表防 Spam 与分组单次渲染
        self.assertIn("function renderChatHistory", self.js)
        self.assertIn("validConvs", self.js)
        self.assertIn('key="grp-${gName}"', self.js)
        self.assertIn('key="${c.id}"', self.js)
        self.assertIn('data-id="${c.id}"', self.js)

        # 触摸顺滑滚动
        self.assertIn("-webkit-overflow-scrolling: touch !important;", self.css)
        self.assertIn("overflow-y: auto !important;", self.css)

    def test_core_3_hardware_acceleration_and_resizing(self):
        # GPU 硬件加速
        self.assertIn("backface-visibility: hidden;", self.css)
        self.assertIn("transform: translate3d(0, 0, 0);", self.css)
        self.assertIn("will-change: width, transform;", self.css)

        # Resizing 期间禁用动画
        self.assertIn("body.is-resizing", self.css)
        self.assertIn("transition: none !important;", self.css)

        # JS 拖拽与 Splitter
        self.assertIn("initSplitResizer", self.js)
        self.assertIn("artifactResizer", self.html)
        self.assertIn(".split-resizer", self.css)
        self.assertIn("pointerdown", self.js)
        self.assertIn("is-resizing", self.js)

    def test_core_4_standalone_panels_equality(self):
        # 三大流水线 standalone-view
        self.assertIn('class="pipeline-panel standalone-view" id="reconcilePipeline"', self.html)
        self.assertIn('class="pipeline-panel standalone-view" id="pricePipeline"', self.html)
        self.assertIn('class="pipeline-panel standalone-view" id="reviewPipeline"', self.html)

        # 全屏毛玻璃 Modal 样式
        self.assertIn(".standalone-view", self.css)
        self.assertIn("position: absolute !important;", self.css)
        self.assertIn("z-index: 1000 !important;", self.css)
        self.assertIn("backdrop-filter: blur(24px) saturate(180%) !important;", self.css)
        self.assertIn("max-width: min(1000px, 92%) !important;", self.css)
        self.assertIn("border-radius: 16px !important;", self.css)

        # 背景防穿透遮罩与类名
        self.assertIn("has-pipeline-open", self.css)
        self.assertIn("has-pipeline-open", self.js)
        self.assertIn("main-chat-wrapper", self.html)
        self.assertIn("central-banner", self.html)
        self.assertIn("dashboard-carousel", self.html)

        # 别名解析
        self.assertIn("#对账汇总-panel", self.js)
        self.assertIn("#比选比价-panel", self.js)
        self.assertIn("#合同审查-panel", self.js)

if __name__ == "__main__":
    unittest.main()
