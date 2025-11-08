# construction_scraper_project 2

#管理画面ログイン
メールアドレス：testadmin@example.com
パスワード：testpass

#dashboard（/templates/dashboard）はbase.html（/templates/dashboard/base.html）をベースにして作成しています。

{% block content %}{% endblock %}
の中にコンテンツが入ります。

#各ページのCSS適応方法
/templates/dashboard/scraping/index.htmlを参考にしてください。
{% block head %}
{% endblock %}
の中にCSSファイルを挿入します。