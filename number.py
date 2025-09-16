"""
Flask implementation of the full two-player number guessing game with advanced
features (traps, hints, cooldowns, logs) ported to web.

Usage:
  python number_full.py
Then visit http://localhost:5000/ to play the advanced game in your browser.
"""

from flask import Flask, session, request, redirect, url_for, render_template_string
import random
import os

# ===== CONSTANTS =====
NUM_MIN = 1
NUM_MAX = 50
HIDDEN_MIN = 1
HIDDEN_MAX = 30

app = Flask(__name__)
app.secret_key = 'imigawakaranai'

# ===== Utility =====
def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

# NOTE: Flask session is JSON-serialized. Dict keys must be strings.
# Use 'p1' / 'p2' for per-player maps.

# ===== Game state management =====
def init_game_state(allow_negative: bool, target_points: int):
    if allow_negative:
        eff_num_min, eff_num_max = -NUM_MAX, NUM_MAX
        eff_hidden_min, eff_hidden_max = -HIDDEN_MAX, HIDDEN_MAX
    else:
        eff_num_min, eff_num_max = NUM_MIN, NUM_MAX
        eff_hidden_min, eff_hidden_max = HIDDEN_MIN, HIDDEN_MAX

    session.update({
        'allow_negative': allow_negative,
        'eff_num_min': eff_num_min,
        'eff_num_max': eff_num_max,
        'eff_hidden_min': eff_hidden_min,
        'eff_hidden_max': eff_hidden_max,
        'target_points': target_points,
        'score1': 0,
        'score2': 0,
        'round_no': 1,
        'turn': 1,  # 1 or 2
        'secret1': None,
        'secret2': None,
        'hidden_secret': None,
        'available_hints': {'p1': ['和','差','積'], 'p2': ['和','差','積']},
        'hint_choice_available': {'p1': False, 'p2': False},  # make True for the second player each round
        'cooldown': {'p1': 0, 'p2': 0},
        'trap_kill': {'p1': [], 'p2': []},
        'trap_info': {'p1': [], 'p2': []},
        'pending_view': {'p1': False, 'p2': False},
        'can_view': {'p1': False, 'p2': False},
        'view_cut_index': {'p1': None, 'p2': None},
        'skip_next_turn': {'p1': False, 'p2': False},
        'actions_log': [],
        'phase': 'setup',
        'winner': None,
    })

def pid_key(pid: int) -> str:
    return 'p1' if pid == 1 else 'p2'

# ===== Routes =====
@app.route('/')
def index():
    return redirect(url_for('full_game'))

@app.route('/full', methods=['GET', 'POST'])
def full_game():
    phase = session.get('phase', 'setup')

    # -------- setup --------
    if phase == 'setup':
        if request.method == 'POST':
            p1_name = request.form.get('p1_name', 'プレイヤー1')
            p2_name = request.form.get('p2_name', 'プレイヤー2')
            target_points = int(request.form.get('target_points', 3))
            allow_negative = request.form.get('allow_negative', 'n') == 'y'
            session['p1_name'] = p1_name
            session['p2_name'] = p2_name
            init_game_state(allow_negative, target_points)
            session['hint_choice_available']['p2'] = True  # 後攻のみ種類指定可
            session['phase'] = 'secrets1'
            return redirect(url_for('full_game'))
        return render_template_string('''
            <h2>ゲーム初期設定</h2>
            <form method="post">
                <label>プレイヤー1の名前: <input name="p1_name"></label><br/>
                <label>プレイヤー2の名前: <input name="p2_name"></label><br/>
                <label>先取ポイント: <input type="number" name="target_points" min="1" value="3"></label><br/>
                <label>負の数を許可しますか？ [y/n]:
                    <select name="allow_negative"><option value="n">n</option><option value="y">y</option></select>
                </label><br/>
                <button type="submit">開始</button>
            </form>
        ''')

    # -------- secrets1 --------
    if phase == 'secrets1':
        if request.method == 'POST':
            eff_min = session['eff_num_min']
            eff_max = session['eff_num_max']
            try:
                secret1 = int(request.form['secret1'])
            except Exception:
                secret1 = None
            if secret1 is not None and eff_min <= secret1 <= eff_max:
                session['secret1'] = secret1
                session['phase'] = 'secrets2'
                return redirect(url_for('full_game'))
            msg = f'{eff_min}〜{eff_max}の整数を入力してください。'
            return render_template_string('''
                <p style="color:red;">{{msg}}</p>
                <form method="post">
                    <label>{{ p1_name }} の秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                        <input type="number" name="secret1" required></label><br/>
                    <button type="submit">次へ</button>
                </form>
            ''', msg=msg, p1_name=session['p1_name'], eff_min=eff_min, eff_max=eff_max)
        return render_template_string('''
            <h2>{{ p1_name }} の秘密の数字を決めてください</h2>
            <form method="post">
                <label>秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                    <input type="number" name="secret1" required></label><br/>
                <button type="submit">次へ</button>
            </form>
        ''', p1_name=session['p1_name'], eff_min=session['eff_num_min'], eff_max=session['eff_num_max'])

    # -------- secrets2 --------
    if phase == 'secrets2':
        if request.method == 'POST':
            eff_min = session['eff_num_min']
            eff_max = session['eff_num_max']
            try:
                secret2 = int(request.form['secret2'])
            except Exception:
                secret2 = None
            if secret2 is not None and eff_min <= secret2 <= eff_max:
                session['secret2'] = secret2
                # ラウンド用初期化
                session['hidden_secret'] = random.randint(session['eff_hidden_min'], session['eff_hidden_max'])
                session['tries1'] = 0
                session['tries2'] = 0
                session['actions_log'] = []
                session['trap_kill'] = {'p1': [], 'p2': []}
                session['trap_info'] = {'p1': [], 'p2': []}
                session['pending_view'] = {'p1': False, 'p2': False}
                session['can_view'] = {'p1': False, 'p2': False}
                session['view_cut_index'] = {'p1': None, 'p2': None}
                session['skip_next_turn'] = {'p1': False, 'p2': False}
                session['cooldown'] = {'p1': 0, 'p2': 0}
                session['available_hints'] = {'p1': ['和','差','積'], 'p2': ['和','差','積']}
                session['hint_choice_available'] = {'p1': False, 'p2': True}
                session['winner'] = None
                session['phase'] = 'play'
                return redirect(url_for('full_game'))
            msg = f'{eff_min}〜{eff_max}の整数を入力してください。'
            return render_template_string('''
                <p style="color:red;">{{msg}}</p>
                <form method="post">
                    <label>{{ p2_name }} の秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                        <input type="number" name="secret2" required></label><br/>
                    <button type="submit">次へ</button>
                </form>
            ''', msg=msg, p2_name=session['p2_name'], eff_min=eff_min, eff_max=eff_max)
        return render_template_string('''
            <h2>{{ p2_name }} の秘密の数字を決めてください</h2>
            <form method="post">
                <label>秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                    <input type="number" name="secret2" required></label><br/>
                <button type="submit">開始</button>
            </form>
        ''', p2_name=session['p2_name'], eff_min=session['eff_num_min'], eff_max=session['eff_num_max'])

    # -------- play --------
    if phase == 'play':
        if session.get('winner'):
            session['phase'] = 'end_round'
            return redirect(url_for('full_game'))

        player_id = session['turn']
        k = pid_key(player_id)

        # 次ターンスキップ処理
        if session['skip_next_turn'][k]:
            session['skip_next_turn'][k] = False
            name = session['p1_name'] if player_id == 1 else session['p2_name']
            session['actions_log'].append(f"{name} のターンは近接トラップ効果でスキップ")
            return switch_turn_and_redirect(player_id)

        # 各アクションのフォームからだけ受け取る（不足なら無視して再描画）
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'g' and 'guess' in request.form:
                return handle_guess(player_id, int(request.form['guess']))
            elif action == 'h':
                return handle_hint(player_id, request.form)
            elif action == 'c' and 'new_secret' in request.form:
                return handle_change(player_id, int(request.form['new_secret']))
            elif action == 't':
                return handle_trap(player_id, request.form)

        p1_name = session['p1_name']
        p2_name = session['p2_name']
        name = p1_name if player_id == 1 else p2_name
        eff_min = session['eff_num_min']
        eff_max = session['eff_num_max']
        c_available = session['cooldown'][k] == 0
        hint_available = bool(session['available_hints'][k]) or session['hint_choice_available'][k]

        return render_template_string('''
            <h2>{{ round_no }} ラウンド目</h2>
            <p>現在のスコア: {{ p1_name }} {{ score1 }} - {{ score2 }} {{ p2_name }}</p>
            <p><strong>{{ name }}</strong> のターンです。</p>

            <h3>アクション</h3>
            <!-- g: 予想 -->
            <form method="post" style="margin-bottom:1em;">
                <input type="hidden" name="action" value="g">
                相手の数字を予想: <input type="number" name="guess" required>
                <button type="submit">予想する</button>
            </form>

            <!-- h: ヒント -->
            {% if hint_available %}
            <form method="post" style="margin-bottom:1em;">
                <input type="hidden" name="action" value="h">
                <label><input type="checkbox" name="confirm_choice"> 種類を指定する</label>
                <select name="hint_type">
                    <option value="和">和</option>
                    <option value="差">差</option>
                    <option value="積">積</option>
                </select>
                <button type="submit">ヒントをもらう</button>
            </form>
            {% else %}
            <p>（このラウンドのヒントは出尽くしました）</p>
            {% endif %}

            <!-- c: 自分の数を変更 -->
            {% if c_available %}
            <form method="post" style="margin-bottom:1em;">
                <input type="hidden" name="action" value="c">
                新しい自分の数 ({{ eff_min }}-{{ eff_max }}):
                <input type="number" name="new_secret" required>
                <button type="submit">変更する</button>
            </form>
            {% else %}
            <p>（c はクールダウン中のため使用不可）</p>
            {% endif %}

            <!-- t: トラップ設定 -->
            <form method="post" style="margin-bottom:1em;">
                <input type="hidden" name="action" value="t">
                <label><input type="radio" name="trap_kind" value="k" checked> kill（即負け）</label>
                <label><input type="radio" name="trap_kind" value="i"> info（情報）</label><br>
                <div>
                  kill用: <input type="number" name="trap_kill_value" placeholder="kill数">
                </div>
                <div>
                  info用（空欄可・最大5個まで追加）:
                  <input type="number" name="trap_info_value_0" placeholder="info1">
                  <input type="number" name="trap_info_value_1" placeholder="info2">
                  <input type="number" name="trap_info_value_2" placeholder="info3">
                </div>
                <button type="submit">トラップを設定</button>
            </form>

            <h3>アクション履歴</h3>
            <ul>
                {% for entry in actions_log %}
                  <li>{{ entry }}</li>
                {% endfor %}
            </ul>
        ''', name=name, p1_name=p1_name, p2_name=p2_name,
           score1=session['score1'], score2=session['score2'], round_no=session['round_no'],
           hint_available=hint_available, c_available=c_available,
           actions_log=session['actions_log'], eff_min=eff_min, eff_max=eff_max)

    # -------- end_round --------
    if phase == 'end_round':
        p1_name = session['p1_name']
        p2_name = session['p2_name']
        p1_score = session['score1']
        p2_score = session['score2']
        target = session['target_points']
        match_over = p1_score >= target or p2_score >= target
        if request.method == 'POST':
            if match_over:
                final_message = f"マッチ終了! {p1_name} {p1_score} - {p2_score} {p2_name}"
                session.clear()
                return final_message
            else:
                session['round_no'] += 1
                session['secret1'] = None
                session['secret2'] = None
                session['hidden_secret'] = None
                # 負けた方が先行
                session['turn'] = 2 if session['winner'] == 1 else 1
                session['phase'] = 'secrets1'
                return redirect(url_for('full_game'))
        return render_template_string('''
            <h2>ラウンド {{ round_no }} の結果</h2>
            <p>勝者: {{ winner_name }} ({{ tries }} 回で当てました)</p>
            <p>このラウンドの数: {{ p1_name }}={{ secret1 }}, {{ p2_name }}={{ secret2 }}, 隠し数={{ hidden_secret }}</p>
            <p>現在のスコア: {{ p1_name }} {{ score1 }} - {{ score2 }} {{ p2_name }}</p>
            {% if match_over %}
              <form method="post">
                <button type="submit">マッチ終了</button>
              </form>
            {% else %}
              <form method="post">
                <button type="submit">次のラウンドへ</button>
              </form>
            {% endif %}
        ''', round_no=session['round_no'], winner_name=session['p1_name'] if session['winner']==1 else session['p2_name'],
           tries=session['tries1'] if session['winner']==1 else session['tries2'],
           secret1=session['secret1'], secret2=session['secret2'], hidden_secret=session['hidden_secret'],
           p1_name=p1_name, p2_name=p2_name, score1=p1_score, score2=p2_score, match_over=match_over)

    # Fallback
    return redirect(url_for('full_game'))

# ===== Action handlers =====
def handle_guess(player_id: int, guess: int):
    opponent_id = 2 if player_id == 1 else 1
    k_me = pid_key(player_id)
    k_opp = pid_key(opponent_id)
    opponent_secret = session['secret2'] if player_id == 1 else session['secret1']
    my_name = session['p1_name'] if player_id == 1 else session['p2_name']

    if player_id == 1:
        session['tries1'] += 1
    else:
        session['tries2'] += 1

    # 正解優先
    if guess == opponent_secret:
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（正解！相手は即死）")
        if player_id == 1:
            session['score1'] += 1
        else:
            session['score2'] += 1
        session['winner'] = player_id
        return redirect(url_for('full_game'))

    # トラップ判定
    kill_traps = set(session['trap_kill'][k_opp])
    info_traps = set(session['trap_info'][k_opp])

    # kill ±1 即死
    if any(abs(guess - t) <= 1 for t in kill_traps):
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        session['winner'] = opponent_id
        return redirect(url_for('full_game'))

    # info 一致 → 相手が次ターンから閲覧可
    if guess in info_traps:
        session['pending_view'][k_opp] = True
        session['view_cut_index'][k_opp] = len(session['actions_log'])
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（情報トラップ発動）")

    # kill ±5 次ターンスキップ（±1はすでに処理済み）
    if any(abs(guess - t) <= 5 for t in kill_traps):
        session['skip_next_turn'][k_me] = True
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（kill近接±5命中：次ターンスキップ）")
        return switch_turn_and_redirect(player_id)

    # 通常のハズレ
    session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（ハズレ）")
    return switch_turn_and_redirect(player_id)

def handle_hint(player_id: int, form_data):
    my_name = session['p1_name'] if player_id == 1 else session['p2_name']
    k_me = pid_key(player_id)

    choose_type = False
    if session['hint_choice_available'][k_me] and form_data.get('confirm_choice'):
        choose_type = True

    if choose_type:
        hint_type = form_data.get('hint_type')
        session['hint_choice_available'][k_me] = False
    else:
        stock = session['available_hints'][k_me]
        if not stock:
            session['actions_log'].append("（このラウンドのヒントは出尽くしました）")
            return switch_turn_and_redirect(player_id)
        hint_type = random.choice(stock)
        stock.remove(hint_type)

    opponent_secret = session['secret2'] if player_id == 1 else session['secret1']
    hidden_secret = session['hidden_secret']
    if hint_type == '和':
        val = opponent_secret + hidden_secret
    elif hint_type == '差':
        val = abs(opponent_secret - hidden_secret)
    else:
        val = opponent_secret * hidden_secret

    session['actions_log'].append(f"{my_name} が h（ヒント取得）{hint_type}＝{val}")
    return switch_turn_and_redirect(player_id)

def handle_change(player_id: int, new_secret: int):
    eff_min = session['eff_num_min']
    eff_max = session['eff_num_max']
    if not (eff_min <= new_secret <= eff_max):
        return switch_turn_and_redirect(player_id)

    my_name = session['p1_name'] if player_id == 1 else session['p2_name']
    k_me = pid_key(player_id)

    # 自分のトラップと衝突しないか
    my_traps = set(session['trap_kill'][k_me]) | set(session['trap_info'][k_me])
    if new_secret in my_traps:
        session['actions_log'].append("⚠ その数字は現在のトラップに含まれています。別の数字を選んでください。")
        return switch_turn_and_redirect(player_id)

    if player_id == 1:
        session['secret1'] = new_secret
        session['cooldown']['p1'] = 2
        session['available_hints']['p2'] = ['和','差','積']
    else:
        session['secret2'] = new_secret
        session['cooldown']['p2'] = 2
        session['available_hints']['p1'] = ['和','差','積']
    session['actions_log'].append(f"{my_name} が c（自分の数を変更）→ {new_secret}")
    return switch_turn_and_redirect(player_id)

def handle_trap(player_id: int, form_data):
    tkind = form_data.get('trap_kind')
    my_name = session['p1_name'] if player_id == 1 else session['p2_name']
    eff_min = session['eff_num_min']
    eff_max = session['eff_num_max']
    my_secret = session['secret1'] if player_id == 1 else session['secret2']
    k_me = pid_key(player_id)
    my_kill = session['trap_kill'][k_me]
    my_info = session['trap_info'][k_me]

    def read_trap_value(raw):
        try:
            val = int(raw)
        except Exception:
            raise ValueError
        if not (eff_min <= val <= eff_max):
            raise ValueError
        if val == my_secret or (session['allow_negative'] and abs(val) == abs(my_secret)):
            raise ValueError
        return val

    try:
        if tkind == 'k' and form_data.get('trap_kill_value'):
            tval = read_trap_value(form_data.get('trap_kill_value'))
            my_kill.clear()
            my_kill.append(tval)
            session['actions_log'].append(f"{my_name} が killトラップを {tval} に設定")
        elif tkind == 'i':
            added = []
            for key in ('trap_info_value_0','trap_info_value_1','trap_info_value_2'):
                if form_data.get(key):
                    v = read_trap_value(form_data.get(key))
                    if v not in my_info and len(my_info) < 5:
                        my_info.append(v)
                        added.append(v)
            if added:
                session['actions_log'].append(f"{my_name} が infoトラップを {', '.join(str(v) for v in added)} に設定")
            else:
                session['actions_log'].append("（infoトラップは追加されませんでした）")
        else:
            session['actions_log'].append("⚠ 無効なトラップ種別が選択されました。")
    except ValueError:
        session['actions_log'].append("⚠ 無効な数字が入力されました。")
    return switch_turn_and_redirect(player_id)

def switch_turn_and_redirect(current_player: int):
    # クールダウンを1減らす
    for k in ('p1','p2'):
        if session['cooldown'][k] > 0:
            session['cooldown'][k] -= 1

    # 情報トラップの閲覧権限を昇格（相手の次ターン開始時）
    if current_player == 1:
        if session['pending_view']['p2']:
            session['can_view']['p2'] = True
            session['pending_view']['p2'] = False
    else:
        if session['pending_view']['p1']:
            session['can_view']['p1'] = True
            session['pending_view']['p1'] = False

    # 手番交代
    session['turn'] = 2 if current_player == 1 else 1
    return redirect(url_for('full_game'))

# ===== Entry point =====
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
