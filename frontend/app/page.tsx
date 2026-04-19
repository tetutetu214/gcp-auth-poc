"use client";

import { useState } from "react";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [uploadMessage, setUploadMessage] = useState<string>("");
  const [uploadLoading, setUploadLoading] = useState<boolean>(false);

  const [mailMessage, setMailMessage] = useState<string>("");
  const [mailLoading, setMailLoading] = useState<boolean>(false);

  const handleUpload = async () => {
    if (!file) {
      setUploadMessage("ファイルを選択してください");
      return;
    }
    setUploadLoading(true);
    setUploadMessage("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setUploadMessage(data.message ?? JSON.stringify(data));
    } catch {
      setUploadMessage("エラーが発生しました");
    } finally {
      setUploadLoading(false);
    }
  };

  const handleFetchMail = async () => {
    setMailLoading(true);
    setMailMessage("");
    try {
      const res = await fetch("/api/graph/sync");
      const data = await res.json();
      if (data.status === "auth_required") {
        // Entra ID の同意画面へ遷移
        window.location.href = data.authorize_url;
        return;
      }
      if (data.status === "ok") {
        setMailMessage(`取得成功：${data.count}件 / ${data.gcs_path}`);
      } else {
        setMailMessage(`エラー：${JSON.stringify(data)}`);
      }
    } catch {
      setMailMessage("通信エラーが発生しました");
    } finally {
      setMailLoading(false);
    }
  };

  return (
    <main style={{ padding: "2rem" }}>
      <h1>PDF アップロード PoC</h1>
      <input
        type="file"
        accept="application/pdf"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <br /><br />
      <button onClick={handleUpload} disabled={uploadLoading}>
        {uploadLoading ? "アップロード中..." : "アップロード"}
      </button>
      {uploadMessage && <p>{uploadMessage}</p>}

      <hr style={{ margin: "2rem 0" }} />

      <h2>メール取得 PoC</h2>
      <p>Microsoft Graph API で自分の最新メール10件を取得し、GCSに保存します。</p>
      <button onClick={handleFetchMail} disabled={mailLoading}>
        {mailLoading ? "取得中..." : "メールを取得"}
      </button>
      {mailMessage && <p>{mailMessage}</p>}
    </main>
  );
}
