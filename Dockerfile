# ベースとなる公式Pythonイメージを選択
FROM python:3.11-slim

# Tesseract OCRと日本語言語パックをインストール
RUN apt-get update && apt-get install -y tesseract-ocr tesseract-ocr-jpn

# 作業ディレクトリを設定
WORKDIR /app

# 必要なライブラリをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# プログラムのコードをコピー
COPY . .

# アプリケーションを実行するコマンド
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "line_rejection_counter_bot:app"]