import os
from flask import Flask, jsonify, redirect, render_template, request, url_for
from code_stats import analyze_uploads, MAX_REQUEST, MAX_UPLOAD, MAX_FILES
from url_source import analyze_url

app = Flask(__name__)
app.config.update(MAX_CONTENT_LENGTH=MAX_REQUEST, MAX_FORM_PARTS=1200,
                  SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(32)


@app.get('/')
def index():
    return render_template('home.html')


@app.get('/history')
def history():
    return render_template('history.html')


@app.get('/arithmetic')
@app.post('/arithmetic/submit')
def legacy_arithmetic():
    return redirect(url_for('math_practice.practice'), code=303)


@app.get('/game24')
@app.get('/game24/solution')
@app.post('/game24/check')
def legacy_game24():
    return redirect(url_for('game_24.play'), code=303)


@app.context_processor
def inject_profile():
    from group_site import load_team, member_avatar
    team = load_team()
    for member in team['members']:
        member['avatar_url'] = member_avatar(member['id'])
    return {'profile': team, 'team': team, 'upload_limit': MAX_UPLOAD, 'max_files': MAX_FILES}


@app.get('/code-stats')
def code_stats():
    return render_template('code_stats.html')


@app.get('/math')
def math_home():
    return render_template('math.html')


@app.post('/api/analyze')
def analyze():
    uploads = request.files.getlist('files')
    if not uploads or all(not f.filename for f in uploads):
        return jsonify(error='请先选择代码文件、文件夹或 ZIP'), 400
    try:
        return jsonify(analyze_uploads(uploads))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


@app.errorhandler(413)
def upload_too_large(error):
    return jsonify(error='上传请求过大或文件过多；文件总大小上限为 1 GB，请分批统计'), 413


@app.post('/api/analyze-url')
def analyze_remote_source():
    request.max_content_length = 16 * 1024
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error='请填写需要统计的网址'), 400
    try:
        return jsonify(analyze_url(data.get('url')))
    except ValueError as exc:
        return jsonify(error=str(exc)), 400


from math_practice import bp as math_practice_bp
from game_24 import bp as game24_bp
from dice_game import bp as dice_bp
app.register_blueprint(math_practice_bp)
app.register_blueprint(game24_bp)
app.register_blueprint(dice_bp)
from group_site import register_group_routes
register_group_routes(app)

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5050')), debug=False)
