# 建設業 企業情報スクレイパー（最大100件）

## 使い方（ローカル）
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
# ブラウザ: http://localhost:7700
```

## Dockerでの使い方
```bash
docker compose up -d --build
# ブラウザ: http://localhost:9020
```

### メモ
- robots.txt を尊重します（取得禁止のURLはスキップ）
- 1〜1.5秒の待機を入れています
- 企業名/住所/メール/電話はヒューリスティック抽出のため精度に限界があります
- 商用・大量取得は必ずサイト管理者の許可を得てください
