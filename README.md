# construction_scraper_project 2

# test build from Cloud Build

<!-- # test build from Cloud Build：Cloud Build トリガー動作確認用 -->

#管理画面ログイン
メールアドレス：testadmin@example.com
パスワード：testpass

#dashboard（/templates/dashboard）は base.html（/templates/dashboard/base.html）をベースにして作成しています。

{% block content %}{% endblock %}
の中にコンテンツが入ります。

#各ページの CSS 適応方法
/templates/dashboard/scraping/index.html を参考にしてください。
{% block head %}
{% endblock %}
の中に CSS ファイルを挿入します。
