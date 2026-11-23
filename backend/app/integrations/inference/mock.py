from .schemas import ModelResult, TongueFeature

class MockAdapter:
    async def analyze(self, image_path: str, symptoms: str) -> ModelResult:
        # Fixed fixtures only. No image analysis or clinical inference is performed.
        return ModelResult(model_version='mock-fixture-1.0', is_demo=True,
            tongue_features=[TongueFeature(name='舌色', value='舌色偏淡（模拟）'),
                             TongueFeature(name='舌苔', value='苔薄白（模拟）')],
            fusion_result={'summary': '固定演示结果，未对上传图片进行模型推理。',
                           'query_terms': ['舌色偏淡', '苔薄白']})
