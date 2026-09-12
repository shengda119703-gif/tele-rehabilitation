import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from app.exercises import EXERCISE_IDS
from app.exercise_guides import guide_steps
from app.ui.exercise_guide import ExerciseGuide


@pytest.fixture(scope='module')
def qt_app():
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('eid', EXERCISE_IDS)
def test_each_action_has_three_side_specific_image_slots_and_plain_steps(eid, tmp_path):
    left = guide_steps(eid, 'left', root=tmp_path)
    right = guide_steps(eid, 'right', root=tmp_path)
    assert [s['key'] for s in left] == ['start', 'move', 'return']
    assert all(s['text'] and s['alt'] and s['title'] for s in left)
    assert all(s['image_path'].parent.name == 'left' for s in left)
    assert all(s['image_path'].parent.name == 'right' for s in right)
    assert all(not s['image_path'].exists() for s in left)


@pytest.mark.parametrize('eid,side', [('unknown', 'left'), ('../bad', 'left'),
                                      ('wrist_flexion', '../right'), ('wrist_flexion', 'both')])
def test_invalid_image_identity_is_rejected(eid, side):
    with pytest.raises(ValueError):
        guide_steps(eid, side)


def test_guide_has_working_steps_and_missing_image_does_not_block(qt_app, tmp_path):
    guide = ExerciseGuide(root=tmp_path)
    guide.set_exercise('wrist_flexion', 'left')
    guide.show()
    qt_app.processEvents()
    assert '待补充' in guide.picture.text()
    assert '左侧' in guide.side_label.text()
    guide.step_buttons[1].click()
    assert guide.step_index == 1 and '掌侧' in guide.instruction.text()
    guide.next_button.click()
    assert guide.step_index == 2
    guide.previous_button.click()
    assert guide.step_index == 1
    guide.set_exercise('wrist_extension', 'right')
    assert guide.step_index == 0 and '右侧' in guide.side_label.text()
    guide.close()


def test_guide_loads_only_matching_side_image_and_handles_corruption(qt_app, tmp_path):
    path = guide_steps('wrist_flexion', 'left', root=tmp_path)[0]['image_path']
    path.parent.mkdir(parents=True)
    picture = QImage(160, 90, QImage.Format.Format_RGB32)
    picture.fill(0xffabcdef)
    assert picture.save(str(path))
    guide = ExerciseGuide(root=tmp_path)
    guide.set_exercise('wrist_flexion', 'left')
    assert guide.image_available
    guide.set_exercise('wrist_flexion', 'right')
    assert not guide.image_available  # Never reuse the opposite side or mirror it.
    path.write_bytes(b'not a PNG')
    guide.set_exercise('wrist_flexion', 'left')
    assert not guide.image_available and '无法读取' in guide.picture.text()


def test_guide_phase_is_only_visual_and_freezes_on_missing_evidence(qt_app, tmp_path):
    guide = ExerciseGuide(root=tmp_path)
    guide.set_exercise('shoulder_abduction', 'left')
    guide.follow_observation('ONLINE', 'REST', valid=True)
    assert guide.step_index == 1 and '下一步' in guide.status.text()
    guide.follow_observation('ONLINE', 'LOWERING', valid=False)
    assert guide.step_index == 1 and '不足' in guide.status.text()
    guide.follow_observation('ONLINE', 'LOWERING', valid=True, training_stage='PAUSED')
    assert guide.step_index == 1 and '暂停' in guide.status.text()
    guide.follow_observation('OFFLINE', 'LOWERING', valid=True)
    assert guide.step_index == 1 and '中断' in guide.status.text()
    guide.follow_observation('ONLINE', 'LOWERING', valid=True)
    assert guide.step_index == 2
