from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)
    force_web: bool = False


class UrlRequest(BaseModel):
    url: str = Field(min_length=8, max_length=4000)


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
