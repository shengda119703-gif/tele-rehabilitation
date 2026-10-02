from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel,
    QLineEdit, QSpinBox, QPushButton, QTabWidget, QWidget, QCheckBox, QComboBox)
from uuid import uuid4


def blank_health(name=''):
    return dict(name=name, age=0, conditions=[], medications=[], familyContact='', familyPhone='',
                elderPhone='', communityDoctorPhone='', mobility='unknown', usesCane=False,
                nightVision='unknown', cognition='unknown', familySharing='denied')


class ProductProfileDialog(QDialog):
    """First run and editing use the same source-complete local form."""
    def __init__(self, stored=None, participants=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('建立健康档案' if not stored else '个人健康资料')
        self.resize(620, 530)
        self.stored = stored
        self.value = None
        self.profile = dict((stored or {}).get('profile') or blank_health())
        box = QVBoxLayout(self)
        note = QLabel('按真实情况填写。用药按已有医嘱记录；家庭绑定与共享在家庭页单独确认。')
        note.setWordWrap(True)
        box.addWidget(note)
        self.owner = QComboBox()
        self.owner.addItem('新建用户', 'person-'+uuid4().hex)
        for p in participants or []:
            self.owner.addItem(p['display_name']+' · 已有康复用户', p['participant_id'])
        if stored:
            self.owner.addItem(self.profile['name'], stored['ownerId'])
            self.owner.setCurrentIndex(self.owner.count()-1)
            self.owner.setEnabled(False)
        box.addWidget(self.owner)
        self.owner.currentIndexChanged.connect(self._owner_changed)
        self.tabs = QTabWidget()
        box.addWidget(self.tabs)
        self.inputs = {}
        pages = [('基础资料', [('name','称呼'),('conditions','已知健康情况（逗号分隔）'),('elderPhone','本人电话')]),
                 ('康复目标', [('rehabGoal','康复 / 生活目标'),('currentState','当前状态')]),
                 ('家庭与用药', [('familyContact','家庭联系人'),('familyPhone','家属电话'),
                   ('communityDoctorPhone','社区医生电话'),('medications','已有医嘱药物（逗号分隔，可稍后补充）')])]
        for title, fields in pages:
            page = QWidget()
            form = QFormLayout(page)
            for key, label in fields:
                source = (stored or {}).get(key, '') if key in ('rehabGoal','currentState') else self.profile.get(key,'')
                edit = QLineEdit('，'.join(source) if isinstance(source,list) else str(source))
                edit.setMaxLength(1000 if key in ('conditions','rehabGoal','currentState') else 200)
                self.inputs[key] = edit
                form.addRow(label, edit)
            if title == '基础资料':
                self.age = QSpinBox()
                self.age.setRange(0,130)
                self.age.setSpecialValueText('未填写')
                self.age.setValue(self.profile.get('age',0))
                form.addRow('年龄', self.age)
                self.mobility = QComboBox()
                for value,label in [('unknown','未填写'),('independent','通常独立'),('uses_cane','使用拐杖'),('needs_support','需要协助')]:
                    self.mobility.addItem(label,value)
                self.mobility.setCurrentIndex(max(0,self.mobility.findData(self.profile.get('mobility'))))
                form.addRow('行动情况',self.mobility)
            self.tabs.addTab(page,title)
        self.error = QLabel()
        self.error.setWordWrap(True)
        box.addWidget(self.error)
        row = QHBoxLayout()
        later = QPushButton('取消')
        later.clicked.connect(self.reject)
        row.addWidget(later)
        self.save = QPushButton('保存并进入首页')
        self.save.setObjectName('productPrimary')
        self.save.clicked.connect(self._save)
        row.addWidget(self.save)
        box.addLayout(row)
        self.participants = participants or []

    def _owner_changed(self):
        for p in getattr(self,'participants',[]):
            if p['participant_id'] == self.owner.currentData():
                self.inputs['name'].setText(p['display_name'])
                self.inputs['rehabGoal'].setText(p.get('goals',''))
                self.inputs['currentState'].setText(p.get('reason',''))

    def _save(self):
        if not self.inputs['name'].text().strip():
            self.error.setText('请填写称呼。')
            return
        profile = dict(self.profile)
        for key,edit in self.inputs.items():
            if key not in ('rehabGoal','currentState','medications','conditions'):
                profile[key] = edit.text().strip()
        for key in ('conditions','medications'):
            profile[key] = [s.strip() for s in self.inputs[key].text().replace('，',',').split(',') if s.strip()]
        # Existing structured medication records are maintained by MedicationService, not erased by this form.
        if self.stored:
            profile['medications'] = self.profile.get('medications',[])
        profile.update(age=self.age.value(), mobility=self.mobility.currentData(), usesCane=self.mobility.currentData() == 'uses_cane')
        self.value = dict(ownerId=self.owner.currentData(),profile=profile,
                          rehabGoal=self.inputs['rehabGoal'].text().strip(), currentState=self.inputs['currentState'].text().strip())
        self.accept()


class MedicationDialog(QDialog):
    def __init__(self, record=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('药物资料')
        self.record = dict(record or dict(id=uuid4().hex,status='active'))
        self.value = None
        box = QVBoxLayout(self)
        label = QLabel('只记录已有医嘱，不由软件推断剂量或调整用药。')
        label.setWordWrap(True)
        box.addWidget(label)
        form = QFormLayout()
        self.fields = {}
        for key,title in [('name','药物名称'),('dose','已有医嘱剂量'),('purpose','已知用途'),('times','服用时间 / 频次')]:
            field = QLineEdit(self.record.get(key,''))
            field.setMaxLength(300)
            self.fields[key] = field
            form.addRow(title,field)
        box.addLayout(form)
        self.error = QLabel()
        box.addWidget(self.error)
        save = QPushButton('保存')
        save.setObjectName('productPrimary')
        save.clicked.connect(self._save)
        box.addWidget(save)

    def _save(self):
        if not self.fields['name'].text().strip():
            self.error.setText('请填写药物名称。')
            return
        self.value = dict(self.record, **{key:edit.text().strip() for key,edit in self.fields.items()})
        self.accept()
