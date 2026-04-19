"use client";

import { useState } from "react";

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(false);

  const handleUpload = async () => {
    if (!file) {
      setMessage("ファイルを選択してください");
      return;
    }
    setLoading(true);
    setMessage("");
    const formData = new FormData();
    formData.append("file", file);
    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setMessage(data.message ?? JSON.stringify(data));
    } catch (e) {
      setMessage("エラーが発生しました");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main style={{ padding: "2rem" }}>
      <h1>PDF アップロード PoC</h1>
      <input
        type="file"
        accept="application/pdf"
        onChange={(e) =>
          setFile(e.target.files?.[0] ?? null)
        }
      />
      <br /><br />
      <button onClick={handleUpload} disabled={loading}>
        {loading ? "アップロード中..." : "アップロード"}
      </button>
      {message && <p>{message}</p>}
    </main>
  );
}
