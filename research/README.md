# 训练与实验目录

第一阶段舌象图片识别实现及Windows命令见 [stage1.md](stage1.md)。

最新7类清洗副本为 `datasets/clean_v1`，已完成独立复审；[交付说明、类别统计、清洗日志与训练命令](results/clean_v1/README.md)。原始21类数据仍有未解映射与标注问题，不应直接正式训练。

configs保存训练配置，training保存训练实现，evaluation保存指标与实验脚本，results保存结果。此代码包不包含虚构的训练实现或模型权重。

训练完成时，请保存权重、标签映射、输入尺寸、归一化参数、文本分词器、模型版本和依赖版本。按照docs/model-integration.md实现model-service/predictor.py即可接入。
