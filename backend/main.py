from fastapi import FastAPI, UploadFile, File, HTTPException
from google.cloud import storage
import os

app = FastAPI()

BUCKET_NAME = os.environ["BUCKET_NAME"]


@app.get("/health")
def health() -> dict[str, str]:
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """PDFファイルをGCSにアップロードする"""
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="PDFファイルのみ受け付けます",
        )

    client = storage.Client()
    bucket = client.bucket(BUCKET_NAME)
    blob = bucket.blob(f"uploads/{file.filename}")

    contents = await file.read()
    blob.upload_from_string(
        contents, content_type="application/pdf"
    )

    return {
        "message": "アップロード成功",
        "filename": file.filename or "",
    }
