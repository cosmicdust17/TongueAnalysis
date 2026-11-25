from typing import Annotated, Literal
import unicodedata
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

class Input(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)

class LoginIn(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=128)

class WechatIn(Input):
    code: str = Field(min_length=1, max_length=256)

class DevLoginIn(Input):
    role: Literal['user', 'knowledge_admin', 'ops_admin'] = 'user'

class ProfileIn(Input):
    nickname: str = Field(min_length=1, max_length=80)
    gender: Literal['未填写', '男', '女'] = '未填写'
    age: int | None = Field(default=None, ge=1, le=120)

class PasswordIn(Input):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)
    old_password: str = Field(max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

def normalize_symptom(value):
    if not isinstance(value, str):
        return value
    name = ' '.join(unicodedata.normalize('NFKC', value).split())
    if any(unicodedata.category(char).startswith('C') for char in name):
        raise ValueError('症状名称含有无效字符')
    return name

SymptomName = Annotated[str, Field(min_length=1, max_length=80), BeforeValidator(normalize_symptom)]

class AnalysisIn(Input):
    model_config = ConfigDict(str_strip_whitespace=False)
    image_id: str = Field(min_length=1, max_length=36)
    symptoms: str = Field(min_length=1, max_length=200)
    confirmed_symptoms: list[SymptomName] = Field(default_factory=list, max_length=20)
    duration: Literal['近三天', '近一周', '近一个月', '一个月以上'] = '近一周'

    @field_validator('symptoms')
    @classmethod
    def symptoms_not_blank(cls, value):
        if not value.strip():
            raise ValueError('Symptoms cannot be blank')
        return value

class SymptomIn(Input):
    symptom_name: SymptomName

class SymptomCheckinIn(Input):
    level: int = Field(strict=True, ge=0, le=3)

class EntityIn(Input):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal['舌象特征', '症状', '证候']
    text: str = Field(min_length=1, max_length=5000)
    source_id: str = Field(min_length=1, max_length=36)
    aliases: list[str] = Field(default_factory=list, max_length=30)
    status: Literal['draft', 'pending'] = 'draft'

    @field_validator('aliases')
    @classmethod
    def valid_aliases(cls, value):
        if any(not a.strip() or len(a) > 100 for a in value):
            raise ValueError('Alias must contain 1-100 characters')
        return list(dict.fromkeys(a.strip() for a in value))

class RelationIn(Input):
    source: str = Field(min_length=1, max_length=36)
    target: str = Field(min_length=1, max_length=36)
    kind: Literal['相关', '伴随', '支持'] = '相关'
    source_id: str = Field(min_length=1, max_length=36)
    status: Literal['draft', 'pending'] = 'draft'

class DocumentIn(Input):
    title: str = Field(min_length=1, max_length=200)
    citation: str = Field(min_length=1, max_length=3000)
    file_id: str | None = Field(default=None, max_length=36)
    is_demo: bool = False

class UserStatusIn(Input):
    active: bool
