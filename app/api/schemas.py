from pydantic import BaseModel, Field
class ChatRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=2, max_length=4000)
class KnowledgeRequest(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    source: str = Field(min_length=1, max_length=250)
    text: str = Field(min_length=1, max_length=100000)
class RejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
