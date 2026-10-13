统一归档入口现为 `archive/retired-features`；同时保留旧Agent和OCR，见[统一恢复说明](../RETIRED_FEATURES.md)。

# 报告识字与图片指标提取归档

归档前 main：`2f52d6298df70d871a93f4848540202b1c182f62`。完整远端快照：`archive/pre-report-ocr-retirement-20261013`。

报告上传、下载、回收站、原件保存与训练动作识别保留。报告／图片识字和自动提取已退役，健康页手动填写指标，经本人确认保存为manual来源。已有photo来源的历史事实仍保留原来源，不迁移或删除。

## 从 main 撤出的独立文件

- `mobile_rehab/ocr.py`
- `mobile_rehab/ocr_worker.py`
- `mobile_rehab/requirements.ocr.txt`
- `android_offline/web/ocr.js`
- `android_offline/tools/prepare_ocr.ps1`
- `ankang/route1-health-agent/tests/image-health-parser.test.ts`
- `ankang/route1-health-agent/tests/personal-mode-gates.test.ts`
- `ankang/route1-health-agent/docs/health-image-parser.md`
- `ankang/route1-health-agent/src/adapters/RealImageHealthParser.ts`
- `ankang/route1-health-agent/src/adapters/ImageHealthParser.ts`
- `ankang/route1-health-agent/src/adapters/HttpVisionProvider.ts`
- `ankang/route1-health-agent/src/adapters/MockVisionProvider.ts`
- `ankang/route1-health-agent/src/adapters/DemoImageHealthParser.ts`
- `ankang/route1-health-agent/src/adapters/parserSelector.ts`
- `ankang/route1-health-agent/src/adapters/imageNormalizer.ts`

混合文件中的旧按钮、加载器、图片处理分支和旧专项用例也在上述完整快照中。对应当前测试改测原件读写、人物隔离、手动来源和禁用路径。

## 恢复

在独立检出中恢复完整旧功能，以免只恢复单文件而破坏依赖：

```powershell
git fetch origin archive/pre-report-ocr-retirement-20261013
git worktree add ../report-ocr-history 2f52d6298df70d871a93f4848540202b1c182f62
```

查看单文件：

```powershell
git show 2f52d6298df70d871a93f4848540202b1c182f62:mobile_rehab/ocr.py
```

本地已有依赖、模型和用户资料不删除。新安卓构建清掉build/assets中的旧OCR生成物，源码和用户数据目录不清理；新的依赖与加载清单不再包含Tesseract。

保留image.parse／image.confirm请求名的明确拒绝回复，用于旧客户端兼容，不提供识别服务，不调用Provider、不读附件或新增健康记录。构造器第三参数同样仅作旧调用签名兼容，不接任何图片提供商。
