"""FastAPIアプリケーションエントリポイント"""
from fastapi import FastAPI, UploadFile, File, HTTPException
from google.cloud import storage, firestore

from config import load_config
from routes_graph import build_router, GraphDeps


app = FastAPI()
config = load_config()

# Graph API 用ルーターを登録（Firestore / GCS クライアントを1度だけ作る）
_firestore_client = firestore.Client()
_storage_client = storage.Client()
app.include_router(
    build_router(
        GraphDeps(
            config=config,
            firestore_client=_firestore_client,
            storage_client=_storage_client,
        )
    )
)


@app.get("/health")
def health() -> dict[str, str]:
    """ヘルスチェック用エンドポイント"""
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
) -> dict[str, str]:
    """PDFファイルをGCSにアップロードする（既存機能）"""
    if file.content_type != "application/pdf":
        raise HTTPException(
            status_code=400,
            detail="PDFファイルのみ受け付けます",
        )

    bucket = _storage_client.bucket(config.bucket_name)
    blob = bucket.blob(f"uploads/{file.filename}")

    contents = await file.read()
    blob.upload_from_string(
        contents, content_type="application/pdf"
    )

    return {
        "message": "アップロード成功",
        "filename": file.filename or "",
    }
