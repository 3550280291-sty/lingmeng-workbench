# -*- coding: utf-8 -*-
import unittest
import os
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(BASE_DIR, "app", "web")

class TestUiRefactorEdgeCases(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(APP_DIR, "index.html"), "r", encoding="utf-8") as f:
            cls.html = f.read()
        with open(os.path.join(APP_DIR, "style.css"), "r", encoding="utf-8") as f:
            cls.css = f.read()
        with open(os.path.join(APP_DIR, "app.js"), "r", encoding="utf-8") as f:
            cls.js = f.read()

    def test_01_split_toggle_button_class_cleanliness(self):
        """Verify #splitToggleBtn does not contain .icon-btn (which hardcodes 30px grid) but retains .toggle-panel-btn."""
        self.assertIn('class="split-btn toggle-panel-btn" id="splitToggleBtn"', self.html)
        self.assertNotIn('icon-btn split-btn toggle-panel-btn', self.html)
        self.assertIn('height: auto !important;', self.css)
        self.assertIn('min-height: 32px !important;', self.css)

    def test_02_welcome_card_dom_classes_and_badge_protection(self):
        """Verify renderWelcome generates .task-card and .output-card, and badge-pill is shielded from webkit-box."""
        self.assertIn('task-card', self.js)
        self.assertIn('output-card', self.js)
        self.assertIn('card-title', self.js)
        self.assertIn('card-desc', self.js)
        self.assertIn('.badge-pill', self.css)
        self.assertIn('display: inline-flex !important;', self.css)
        self.assertIn('white-space: nowrap !important;', self.css)

    def test_03_no_premature_conversation_creation_on_pipeline_open(self):
        """Verify openReconcilePipeline, openPricePipeline, openReviewPipeline don't trigger ensureConv on modal open."""
        # Find openReconcilePipeline definition
        reconcile_match = re.search(r'async function openReconcilePipeline\(\)\s*\{([^}]+)\}', self.js)
        self.assertIsNotNone(reconcile_match)
        self.assertNotIn('await ensureConv()', reconcile_match.group(1))

        price_match = re.search(r'async function openPricePipeline\(\)\s*\{([^}]+)\}', self.js)
        self.assertIsNotNone(price_match)
        self.assertNotIn('await ensureConv()', price_match.group(1))

        review_match = re.search(r'async function openReviewPipeline\(\)\s*\{([^}]+)\}', self.js)
        self.assertIsNotNone(review_match)
        self.assertNotIn('await ensureConv()', review_match.group(1))

    def test_04_close_pipeline_restores_home_mode_and_placeholder(self):
        """Verify closing standalone pipelines restores general mode when message count is zero."""
        self.assertIn('function closeAllPipelines', self.js)
        self.assertIn('S.mode = "general";', self.js)
        self.assertIn('renderModes();', self.js)

    def test_05_resizer_clamping_and_window_listeners(self):
        """Verify initSplitResizer clamps to minW/maxW and attaches window move/up listeners."""
        self.assertIn('const clamped = Math.min(Math.max(newWidth, minW), maxW);', self.js)
        self.assertIn('window.addEventListener("pointermove", onPointerMove);', self.js)
        self.assertIn('touch-action: none;', self.css)

    def test_06_complete_background_isolation_in_css(self):
        """Verify has-pipeline-open isolates artifact-panel, resizer, msgList, and composer."""
        self.assertIn('body.has-pipeline-open .artifact-panel', self.css)
        self.assertIn('body.has-pipeline-open .split-resizer', self.css)
        self.assertIn('body.has-pipeline-open #msgList', self.css)
        self.assertIn('pointer-events: none !important;', self.css)

    def test_07_init_opens_first_real_conversation(self):
        """Verify startup logic prioritizes conversations with real messages (c.cnt > 0)."""
        self.assertIn('const firstReal = S.convs.find((c) => c.cnt && c.cnt > 0);', self.js)

    def test_08_welcome_cards_static_and_dynamic_dual_insurance(self):
        """Verify 5 cards exist statically in index.html, styled in style.css, and bound via renderWelcome."""
        # Static HTML dual-insurance: 5 cards rendered in index.html to eliminate startup/async blank screen
        self.assertIn('class="cards dashboard-carousel" id="welcomeCards"', self.html)
        self.assertIn('task-card', self.html)
        self.assertIn('output-card', self.html)
        self.assertIn('welcome-layout', self.html)
        self.assertIn('data-mode="merge"', self.html)
        self.assertIn('data-mode="price"', self.html)
        self.assertIn('data-mode="review"', self.html)
        self.assertIn('data-mode="report"', self.html)
        self.assertIn('data-mode="ppt"', self.html)

        # CSS layout rules
        self.assertIn('.welcome-layout', self.css)
        self.assertIn('.welcome-main-col #welcomeCards', self.css)

        # JS binding coverage
        self.assertIn('function renderWelcome()', self.js)
        self.assertIn('function resetView', self.js)
        self.assertIn('function bind()', self.js)

    def test_09_delivery_card_templates_and_switch_main_view_pipeline_isolation(self):
        """Verify delivery cards populate prompt templates, switchMainView isolates pipelines, and JS syntax integrity."""
        # 1. Delivery template generation in renderWelcome
        self.assertIn('金字塔原理', self.js)
        self.assertIn('汇报 PPT 大纲', self.js)

        # 2. switchMainView isolates standalone pipelines
        self.assertIn('pricePipeline.hidden = true;', self.js)
        self.assertIn('reviewPipeline.hidden = true;', self.js)

        # 3. Clean syntax integrity: no broken double-else in toggleArtifact
        self.assertNotIn('} else {\n    hideArtifact();\n  }\n}', self.js)


if __name__ == "__main__":
    unittest.main()

