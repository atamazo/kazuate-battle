"""
Flask implementation of the full two-player number guessing game with advanced
features such as traps and hints. This skeleton illustrates how to port the
console game logic into a web application. The implementation below sets up
routes and data structures needed to support the game, but some sections
require further development to fully replicate the original console game's
functionality.

Usage:
  python number_full.py

Then visit http://localhost:5000/full to play the advanced game in your
browser.
"""

from flask import Flask, session, request, redirect, url_for, render_template_string
import random
import string
import os

# ===== CONSTANTS =====
NUM_MIN = 1
NUM_MAX = 50
HIDDEN_MIN = 1
HIDDEN_MAX = 30

app = Flask(__name__)
app.secret_key = 'imigawakaranai'

# ===== Utility functions =====

def clear_screen():
    """Clears the console. Unused in web version but kept for completeness."""
    os.system('cls' if os.name == 'nt' else 'clear')

# ===== Game state management =====

# In the console version, many variables are kept in the global scope.
# For the web version, we use the Flask session (for single-browser play)
# or a rooms dictionary (for multi-device play) to store all game state.

# For a single-browser advanced game, we will use session variables.

# Helper to initialize a new game state in the session

def init_game_state(allow_negative: bool, target_points: int):
    """Initializes all game state variables in the session."""
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
        'turn': 1,  # 1 for player1's turn, 2 for player2's turn
        # Secret numbers for each round
        'secret1': None,
        'secret2': None,
        'hidden_secret': None,
        # Hint and trap state per player
        'available_hints': {1: ['和', '差', '積'], 2: ['和', '差', '積']},
        'hint_choice_available': {1: False, 2: False},  # set True for the second player each round
        'cooldown': {1: 0, 2: 0},  # cooldown turns for change-number action
        'trap_kill': {1: set(), 2: set()},
        'trap_info': {1: set(), 2: set()},
        'pending_view': {1: False, 2: False},
        'can_view': {1: False, 2: False},
        'view_cut_index': {1: None, 2: None},
        'skip_next_turn': {1: False, 2: False},
        # Logs of actions (strings)
        'actions_log': [],
        # Flags indicating whether the secret numbers have been set for the round
        'phase': 'setup',  # setup -> secrets1 -> secrets2 -> play -> end_round
        'winner': None,
    })

# ===== Route for the full game =====

@app.route('/full', methods=['GET', 'POST'])
def full_game():
    """
    Main entry point for the advanced game. Depending on the phase stored in
    session['phase'], this function renders the appropriate form and
    processes input to advance the game state. The phases are:

    setup    : collect names, target points, and negative-number option
    secrets1 : player 1 inputs their secret number
    secrets2 : player 2 inputs their secret number
    play     : players take turns choosing actions (guess/hint/change/trap)
    end_round: show round results and prepare for the next round or end match
    
    This skeleton implements the setup and secret input phases. The play
    phase includes a simplified action choice and guess handling. To fully
    replicate the original console game, extend the play phase logic to
    implement hints, traps, cooldowns, and logs as described in the original
    Python script.
    """
    phase = session.get('phase', 'setup')

    # Phase: initial setup (names, negative option, target points)
    if phase == 'setup':
        if request.method == 'POST':
            # Collect form data
            p1_name = request.form.get('p1_name', 'プレイヤー1')
            p2_name = request.form.get('p2_name', 'プレイヤー2')
            target_points = int(request.form.get('target_points', 1))
            allow_negative = request.form.get('allow_negative', 'n') == 'y'
            # Save names and initialize game state
            session['p1_name'] = p1_name
            session['p2_name'] = p2_name
            init_game_state(allow_negative, target_points)
            # Second player may choose hint type once per round
            session['hint_choice_available'][2] = True
            # Proceed to secret number selection
            session['phase'] = 'secrets1'
            return redirect(url_for('full_game'))
        # Render setup form
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

    # Phase: player 1 inputs their secret number
    if phase == 'secrets1':
        if request.method == 'POST':
            secret1 = int(request.form['secret1'])
            # Validate input
            eff_min = session['eff_num_min']
            eff_max = session['eff_num_max']
            if eff_min <= secret1 <= eff_max:
                session['secret1'] = secret1
                session['phase'] = 'secrets2'
                return redirect(url_for('full_game'))
            else:
                msg = f'{eff_min}〜{eff_max}の整数を入力してください。'
                # Show error message with form again
                return render_template_string('''
                    <p style="color:red;">{{msg}}</p>
                    <form method="post">
                        <label>{{ p1_name }} の秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                            <input type="number" name="secret1" required></label><br/>
                        <button type="submit">次へ</button>
                    </form>
                ''', msg=msg, p1_name=session['p1_name'], eff_min=eff_min, eff_max=eff_max)
        # Render form to input player 1's secret number
        return render_template_string('''
            <h2>{{ p1_name }} の秘密の数字を決めてください</h2>
            <form method="post">
                <label>秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                    <input type="number" name="secret1" required></label><br/>
                <button type="submit">次へ</button>
            </form>
        ''', p1_name=session['p1_name'], eff_min=session['eff_num_min'], eff_max=session['eff_num_max'])

    # Phase: player 2 inputs their secret number and hidden secret is generated
    if phase == 'secrets2':
        if request.method == 'POST':
            secret2 = int(request.form['secret2'])
            eff_min = session['eff_num_min']
            eff_max = session['eff_num_max']
            if eff_min <= secret2 <= eff_max:
                session['secret2'] = secret2
                # Generate hidden secret for this round
                session['hidden_secret'] = random.randint(session['eff_hidden_min'], session['eff_hidden_max'])
                # Initialize per-round variables
                session['tries1'] = 0
                session['tries2'] = 0
                session['actions_log'] = []
                session['trap_kill'] = {1: set(), 2: set()}
                session['trap_info'] = {1: set(), 2: set()}
                session['pending_view'] = {1: False, 2: False}
                session['can_view'] = {1: False, 2: False}
                session['view_cut_index'] = {1: None, 2: None}
                session['skip_next_turn'] = {1: False, 2: False}
                session['cooldown'] = {1: 0, 2: 0}
                session['available_hints'] = {1: ['和','差','積'], 2: ['和','差','積']}
                session['hint_choice_available'] = {1: False, 2: True}
                session['winner'] = None
                session['phase'] = 'play'
                return redirect(url_for('full_game'))
            else:
                msg = f'{eff_min}〜{eff_max}の整数を入力してください。'
                return render_template_string('''
                    <p style="color:red;">{{msg}}</p>
                    <form method="post">
                        <label>{{ p2_name }} の秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                            <input type="number" name="secret2" required></label><br/>
                        <button type="submit">次へ</button>
                    </form>
                ''', msg=msg, p2_name=session['p2_name'], eff_min=eff_min, eff_max=eff_max)
        # Render form to input player 2's secret number
        return render_template_string('''
            <h2>{{ p2_name }} の秘密の数字を決めてください</h2>
            <form method="post">
                <label>秘密の数字 ({{ eff_min }}-{{ eff_max }}):
                    <input type="number" name="secret2" required></label><br/>
                <button type="submit">開始</button>
            </form>
        ''', p2_name=session['p2_name'], eff_min=session['eff_num_min'], eff_max=session['eff_num_max'])

    # Phase: play - players take turns choosing actions
    if phase == 'play':
        # If round winner is already determined, go to end_round
        if session.get('winner'):
            session['phase'] = 'end_round'
            return redirect(url_for('full_game'))

        # Determine whose turn and check if their turn is skipped
        player_id = session['turn']
        # If skip flag is set, skip this player's turn once
        if session['skip_next_turn'][player_id]:
            session['skip_next_turn'][player_id] = False
            # Log the skipped turn
            session['actions_log'].append(f"{session['p1_name'] if player_id==1 else session['p2_name']} のターンは近接トラップ効果でスキップ")
            # Switch turn
            session['turn'] = 2 if player_id == 1 else 1
            return redirect(url_for('full_game'))

        # Handle form submission: action choice and subsequent action
        if request.method == 'POST':
            action = request.form['action']
            if action == 'g':
                # Guess action: handle guess logic including traps and win condition
                guess_val = int(request.form['guess'])
                return handle_guess(player_id, guess_val)
            elif action == 'h':
                # Hint action
                return handle_hint(player_id, request.form)
            elif action == 'c':
                # Change number action
                return handle_change(player_id, int(request.form['new_secret']))
            elif action == 't':
                # Set trap action
                return handle_trap(player_id, request.form)

        # Prepare data for rendering the play page
        p1_name = session['p1_name']
        p2_name = session['p2_name']
        name = p1_name if player_id == 1 else p2_name
        opponent_name = p2_name if player_id == 1 else p1_name
        eff_min = session['eff_num_min']
        eff_max = session['eff_num_max']
        # Determine available actions based on cooldown/hints
        c_available = session['cooldown'][player_id] == 0
        hint_available = bool(session['available_hints'][player_id]) or session['hint_choice_available'][player_id]
        return render_template_string('''
            <h2>{{ round_no }} ラウンド目</h2>
            <p>現在のスコア: {{ p1_name }} {{ score1 }} - {{ score2 }} {{ p2_name }}</p>
            <p>{{ name }} のターンです。</p>
            <h3>アクションを選んでください</h3>
            <form method="post">
                <select name="action" onchange="this.form.submit();">
                    <option disabled selected>--選択してください--</option>
                    <option value="g">相手の数を当てる</option>
                    {% if hint_available %}<option value="h">ヒントをもらう</option>{% endif %}
                    {% if c_available %}<option value="c">自分の数を変更</option>{% endif %}
                    <option value="t">トラップを仕掛ける</option>
                </select>
            </form>
            <h3>アクション履歴</h3>
            <ul>
                {% for entry in actions_log %}
                  <li>{{ entry }}</li>
                {% endfor %}
            </ul>
        ''', name=name, p1_name=p1_name, p2_name=p2_name,
           score1=session['score1'], score2=session['score2'], round_no=session['round_no'],
           hint_available=hint_available, c_available=c_available, actions_log=session['actions_log'])

    # Phase: end of round - display results and allow continuation or match end
    if phase == 'end_round':
        p1_name = session['p1_name']
        p2_name = session['p2_name']
        p1_score = session['score1']
        p2_score = session['score2']
        # Check if match is over
        target = session['target_points']
        match_over = p1_score >= target or p2_score >= target
        if request.method == 'POST':
            # Prepare next round or finish match
            if match_over:
                # Reset session for a new game (or redirect to setup)
                final_message = f"マッチ終了! {p1_name} {p1_score} - {p2_score} {p2_name}"
                session.clear()
                return final_message
            else:
                # Increment round number, reset secrets, flip starting player (loser starts)
                session['round_no'] += 1
                session['secret1'] = None
                session['secret2'] = None
                session['hidden_secret'] = None
                session['phase'] = 'secrets1'
                # Loser starts next round
                session['turn'] = 2 if session['winner'] == 1 else 1
                return redirect(url_for('full_game'))
        # Show round summary
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

    # Default fallback
    return redirect(url_for('full_game'))

# ===== Helper functions to handle actions =====


def handle_guess(player_id: int, guess: int):
    """Processes a guess made by the current player. Checks for traps, updates
    scores, logs, and determines if the round is won."""
    opponent_id = 2 if player_id == 1 else 1
    opponent_secret = session['secret2'] if player_id == 1 else session['secret1']
    my_name = session['p1_name'] if player_id == 1 else session['p2_name']
    opp_name = session['p2_name'] if player_id == 1 else session['p1_name']
    # Increment tries counter
    if player_id == 1:
        session['tries1'] += 1
    else:
        session['tries2'] += 1
    # Check for correct guess
    if guess == opponent_secret:
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（正解！相手は即死）")
        # Award point and record winner
        if player_id == 1:
            session['score1'] += 1
        else:
            session['score2'] += 1
        session['winner'] = player_id
        return redirect(url_for('full_game'))
    # Check kill traps (±1 immediate defeat)
    kill_traps = session['trap_kill'][opponent_id]
    if any(abs(guess - t) <= 1 for t in kill_traps):
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（killトラップ±1命中＝即敗北）")
        # Opponent wins round
        session['winner'] = opponent_id
        return redirect(url_for('full_game'))
    # Check info traps (exact match)
    info_traps = session['trap_info'][opponent_id]
    if guess in info_traps:
        # Activate pending view for the opponent
        session['pending_view'][opponent_id] = True
        session['view_cut_index'][opponent_id] = len(session['actions_log'])
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（情報トラップ発動）")
    # Check kill traps (±5 skip next turn)
    if any(abs(guess - t) <= 5 for t in kill_traps):
        session['skip_next_turn'][player_id] = True
        session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（kill近接±5命中：次ターンスキップ）")
        return switch_turn_and_redirect(player_id)
    # Normal miss
    session['actions_log'].append(f"{my_name} が g（予想）→ {guess}（ハズレ）")
    return switch_turn_and_redirect(player_id)


def handle_hint(player_id: int, form_data):
    """Processes a hint request. If the player can choose the type of hint,
    the form should include a 'hint_type' field with '和','差','積'.
    Otherwise, a random hint from available stock is selected."""
    my_name = session['p1_name'] if player_id == 1 else session['p2_name']
    # Determine if player can choose
    choose_type = False
    if player_id == 1 and session['hint_choice_available'][1]:
        if form_data.get('confirm_choice'):
            choose_type = True
    if player_id == 2 and session['hint_choice_available'][2]:
        if form_data.get('confirm_choice'):
            choose_type = True
    # If choosing type, expect 'hint_type' param
    if choose_type:
        hint_type = form_data.get('hint_type')
        session['hint_choice_available'][player_id] = False
    else:
        # Random from available stock
        stock = session['available_hints'][player_id]
        if not stock:
            # No hints left
            session['actions_log'].append("（このラウンドのヒントは出尽くしました）")
            return switch_turn_and_redirect(player_id)
        hint_type = random.choice(stock)
        stock.remove(hint_type)
    # Compute hint value
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
    """Processes a change of the player's secret number. Resets opponent hint stock
    and imposes a cooldown of 2 turns for the change-number action."""
    eff_min = session['eff_num_min']
    eff_max = session['eff_num_max']
    my_name = session['p1_name'] if player_id == 1 else session['p2_name']
    # Check if new secret conflicts with own traps
    if player_id == 1:
        my_traps = session['trap_kill'][1] | session['trap_info'][1]
    else:
        my_traps = session['trap_kill'][2] | session['trap_info'][2]
    if new_secret in my_traps:
        session['actions_log'].append("⚠ その数字は現在のトラップに含まれています。別の数字を選んでください。")
        return switch_turn_and_redirect(player_id)
    # Update secret
    if player_id == 1:
        session['secret1'] = new_secret
        session['cooldown'][1] = 2
        # Reset opponent's hint stock
        session['available_hints'][2] = ['和','差','積']
    else:
        session['secret2'] = new_secret
        session['cooldown'][2] = 2
        session['available_hints'][1] = ['和','差','積']
    session['actions_log'].append(f"{my_name} が c（自分の数を変更）→ {new_secret}")
    return switch_turn_and_redirect(player_id)


def handle_trap(player_id: int, form_data):
    """Processes trap setting. A trap can be of type 'k' (kill) or 'i' (info).
    Depending on the form input, set the appropriate trap number(s)."""
    tkind = form_data.get('trap_kind')
    my_name = session['p1_name'] if player_id == 1 else session['p2_name']
    eff_min = session['eff_num_min']
    eff_max = session['eff_num_max']
    my_secret = session['secret1'] if player_id == 1 else session['secret2']
    # Determine which trap set to use
    my_kill = session['trap_kill'][player_id]
    my_info = session['trap_info'][player_id]
    def read_trap_value(key: str):
        val = int(form_data[key])
        if not (eff_min <= val <= eff_max):
            raise ValueError
        # Cannot set trap on own secret or its negative equivalent in negative mode
        if val == my_secret or (session['allow_negative'] and abs(val) == abs(my_secret)):
            raise ValueError
        return val
    try:
        if tkind == 'k':
            tval = read_trap_value('trap_kill_value')
            # Only one kill trap; replace if exists
            my_kill.clear()
            my_kill.add(tval)
            session['actions_log'].append(f"{my_name} が killトラップを {tval} に設定")
        elif tkind == 'i':
            # Add up to 5 info traps
            current = len(my_info)
            values = []
            for idx in range(current, min(5, current + 3)):
                key = f'trap_info_value_{idx}'
                if key in form_data:
                    tval = read_trap_value(key)
                    values.append(tval)
            for v in values:
                my_info.add(v)
            session['actions_log'].append(f"{my_name} が infoトラップを {', '.join(str(v) for v in values)} に設定")
        else:
            session['actions_log'].append("⚠ 無効なトラップ種別が選択されました。")
    except ValueError:
        session['actions_log'].append("⚠ 無効な数字が入力されました。")
    return switch_turn_and_redirect(player_id)


def switch_turn_and_redirect(current_player: int):
    """Helper to switch the turn to the other player and redirect to the play page."""
    # Decrease cooldown counters
    for pid in (1, 2):
        if session['cooldown'][pid] > 0:
            session['cooldown'][pid] -= 1
    # Handle pending view flags: promote pending view to active at start of player's turn
    # This logic ensures that when a player triggers an info trap, the opponent
    # gains view permissions starting on their next turn.
    if current_player == 1:
        if session['pending_view'][2]:
            session['can_view'][2] = True
            session['pending_view'][2] = False
    else:
        if session['pending_view'][1]:
            session['can_view'][1] = True
            session['pending_view'][1] = False
    # Switch turn
    session['turn'] = 2 if current_player == 1 else 1
    return redirect(url_for('full_game'))

# ===== Entry point =====
if __name__ == '__main__':
    # Note: For production use, configure host/port via environment or command line
    app.run(host='0.0.0.0', port=5000, debug=True)
