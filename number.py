import random
import getpass
import os
from datetime import datetime

NUM_MIN = 1      # プレイヤーが選べる数の最小
NUM_MAX = 50     # プレイヤーが選べる数の最大
HIDDEN_MIN = 1   # 誰にも知られない隠し数の最小
HIDDEN_MAX = 30  # 誰にも知られない隠し数の最大（ソロと合わせて30）

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

print("対戦モード！")
print("ルール: 各プレイヤーは自分の秘密の数字を決め、相手の数を当てたら1ポイント！")

ans = input("このゲームで負の数（マイナス）を許可しますか？ [y/n]: ").strip().lower()
allow_negative = (ans == 'y')
if allow_negative:
    eff_NUM_MIN, eff_NUM_MAX = -NUM_MAX, NUM_MAX
    eff_HIDDEN_MIN, eff_HIDDEN_MAX = -HIDDEN_MAX, HIDDEN_MAX
else:
    eff_NUM_MIN, eff_NUM_MAX = NUM_MIN, NUM_MAX
    eff_HIDDEN_MIN, eff_HIDDEN_MAX = HIDDEN_MIN, HIDDEN_MAX

# ニックネーム設定（未入力ならデフォルト名）
p1_name = input("プレイヤー1のニックネームを入力（未入力なら プレイヤー1）: ").strip() or "プレイヤー1"
p2_name = input("プレイヤー2のニックネームを入力（未入力なら プレイヤー2）: ").strip() or "プレイヤー2"
print(f"対戦カード: {p1_name} vs {p2_name}")

# 先取ポイントを選択（1なら一発勝負）
while True:
    s = input("何ラウンド先取で勝ちにしますか？（例：3 / 1なら一発勝負）: ").strip()
    try:
        target_points = int(s)
        if target_points >= 1:
            break
    except ValueError:
        pass
    print("⚠ 1以上の整数で入力してください。")

score1 = 0
score2 = 0
round_no = 1



# 自分ターンに［自分の行動履歴］と［自分のトラップ］を表示するか（各プレイヤー個別設定）
while True:
    ans = input(f"{p1_name} のターンで［自分の行動履歴］と［自分のトラップ］を表示しますか？ [y/n]: ").strip().lower()
    if ans in ("y", "n"):
        break
    print("⚠ y または n を入力してください。")
p1_show_self_panel = (ans == 'y')
while True:
    ans = input(f"{p2_name} のターンで［自分の行動履歴］と［自分のトラップ］を表示しますか？ [y/n]: ").strip().lower()
    if ans in ("y", "n"):
        break
    print("⚠ y または n を入力してください。")
p2_show_self_panel = (ans == 'y')


starter = 1  # 初回の先行はプレイヤー1。以降は「前ラウンドで負けた方」が先行

while score1 < target_points and score2 < target_points:
    clear_screen()
    print(f"===== ラウンド {round_no} 開始 =====")
    print(f"★ スコア: {p1_name} {score1} - {score2} {p2_name}  (先に {target_points} 点で勝利)\n")

    # 誰にも見えないランダム数字（毎ラウンド更新）
    hidden_secret = random.randint(eff_HIDDEN_MIN, eff_HIDDEN_MAX)

    # 各プレイヤーが自分で秘密の数字を決める（見える入力）
    while True:
        try:
            s = input(f"{p1_name}、自分の秘密の数字を{eff_NUM_MIN}〜{eff_NUM_MAX}で決めて入力してください: ")
            secret1 = int(s)
            if eff_NUM_MIN <= secret1 <= eff_NUM_MAX:
                break
        except ValueError:
            pass
        print(f"⚠ {eff_NUM_MIN}〜{eff_NUM_MAX}の整数で入力してください。")
    input(f"▶ {p2_name} に交代（Enterで画面を隠す）")
    clear_screen()

    while True:
        try:
            s = input(f"{p2_name}、自分の秘密の数字を{eff_NUM_MIN}〜{eff_NUM_MAX}で決めて入力してください: ")
            secret2 = int(s)
            if eff_NUM_MIN <= secret2 <= eff_NUM_MAX:
                break
        except ValueError:
            pass
        print(f"⚠ {eff_NUM_MIN}〜{eff_NUM_MAX}の整数で入力してください。")
    input("▶ ゲーム開始！（Enterで画面を隠す）")
    # ここで対戦カードを再掲しても良い
    clear_screen()

    tries1 = 0
    tries2 = 0

    actions_log_all = []  # 全行動を記録する（履歴表示やinfoトラップ用）

    # ラウンド内のみ有効なトラップ数字（プレイヤーごと・種類別）
    # A: 即負けトラップ（踏むと相手が即敗北）
    trap1_kill_set = set()
    trap2_kill_set = set()
    # B: 情報トラップ（踏むと設置者が相手の行動履歴を見られる）
    trap1_info_set = set()
    trap2_info_set = set()

    # 情報トラップ発動後の閲覧フラグ
    # active: 実際に閲覧可 / pending: 次の自分のターン開始時にactiveへ昇格
    can_view_opponent_full_history_p1 = False
    can_view_opponent_full_history_p2 = False
    pending_view_opponent_full_history_p1 = False
    pending_view_opponent_full_history_p2 = False
    # 情報トラップの可視開始インデックス（actions_log_all の何件目以降を見せるか）
    view_cut_index_p1 = None
    view_cut_index_p2 = None

    # 近接（±5）命中で次ターンをスキップするフラグ
    skip_next_turn_p1 = False
    skip_next_turn_p2 = False

    # ログ追加ヘルパー（全員共通のフルログのみ）
    def append_log(entry: str, pid: int):
        # 常に記録（全員共通のフルログ）
        actions_log_all.append(entry)

    cooldown1 = 0  # プレイヤー1の c 行動のクールダウン（自分の番の回数で数える）
    cooldown2 = 0  # プレイヤー2の c 行動のクールダウン
    if starter == 1:
        # 先行: P1 / 後攻: P2 → 後攻のみ種類指定可
        p1_hint_choice_available = False
        p2_hint_choice_available = True
    else:
        # 先行: P2 / 後攻: P1 → 後攻のみ種類指定可
        p1_hint_choice_available = True
        p2_hint_choice_available = False

    available_hints_p1 = ["和", "差", "積"]
    available_hints_p2 = ["和", "差", "積"]

    winner = None

    def player_turn(player_id):
        global secret1, secret2, tries1, tries2, winner, cooldown1, cooldown2, p1_hint_choice_available, p2_hint_choice_available
        global trap1_kill_set, trap2_kill_set, trap1_info_set, trap2_info_set
        global can_view_opponent_full_history_p1, can_view_opponent_full_history_p2
        global pending_view_opponent_full_history_p1, pending_view_opponent_full_history_p2
        global view_cut_index_p1, view_cut_index_p2
        global skip_next_turn_p1, skip_next_turn_p2
        if player_id == 1:
            my_name = p1_name
            opp_name = p2_name
            opponent_secret = secret2
            my_hints = available_hints_p1
        else:
            my_name = p2_name
            opp_name = p1_name
            opponent_secret = secret1
            my_hints = available_hints_p2

        # 情報トラップ効果の発動タイミング：
        # 相手が引っかかった “次の自分のターン開始時” に有効化
        if player_id == 1 and pending_view_opponent_full_history_p1:
            can_view_opponent_full_history_p1 = True
            pending_view_opponent_full_history_p1 = False
        if player_id == 2 and pending_view_opponent_full_history_p2:
            can_view_opponent_full_history_p2 = True
            pending_view_opponent_full_history_p2 = False

        # 自分のターン開始時にクールダウンを1減らす
        if player_id == 1:
            if cooldown1 > 0:
                cooldown1 -= 1
            c_available = (cooldown1 == 0)
        else:
            if cooldown2 > 0:
                cooldown2 -= 1
            c_available = (cooldown2 == 0)

        # 近接トラップ（±5）命中ペナルティ：このプレイヤーの次ターンをスキップ
        if player_id == 1 and skip_next_turn_p1:
            skip_next_turn_p1 = False
            print("⏭ 近接トラップの効果でこのターンはスキップされます。")
            append_log(f"{my_name} のターンは近接トラップ効果でスキップ", player_id)
            return
        if player_id == 2 and skip_next_turn_p2:
            skip_next_turn_p2 = False
            print("⏭ 近接トラップの効果でこのターンはスキップされます。")
            append_log(f"{my_name} のターンは近接トラップ効果でスキップ", player_id)
            return

        print(f"［範囲］選べる数: {eff_NUM_MIN}〜{eff_NUM_MAX} / 隠し数: {eff_HIDDEN_MIN}〜{eff_HIDDEN_MAX}")

        # 自分の行動履歴と、相手が g（予想）した内容を表示
        my_hist = [e for e in actions_log_all if e.startswith(f"{my_name} ")]
        opp_guess_hist = [e for e in actions_log_all if e.startswith(f"{opp_name} が g（予想）→")]

        # 自分の行動履歴と自分のトラップの表示はプレイヤーごとの設定に従う
        my_show_panel = p1_show_self_panel if player_id == 1 else p2_show_self_panel
        if my_show_panel:
            # 自分の現在の秘密の数を表示
            my_secret_now = secret1 if player_id == 1 else secret2
            print(f"［自分の数］{my_secret_now}")
            print("［自分の行動履歴］")
            if my_hist:
                prefix = f"{my_name} が "
                for e in my_hist:
                    shown = e[len(prefix):] if e.startswith(prefix) else e
                    print(" -", shown)
            else:
                print(" - （まだ行動なし）")
        
        print("［相手の予想履歴（あなたに対して）］")
        if opp_guess_hist:
            for e in opp_guess_hist:
                print(" -", e)
        else:
            print(" - （まだ予想なし）")

        # 情報トラップが発動済みなら、相手の行動履歴（フル）を表示
        if (player_id == 1 and can_view_opponent_full_history_p1) or (player_id == 2 and can_view_opponent_full_history_p2):
            # 可視開始位置（トラップ発動時点）以降のみを表示
            cut = view_cut_index_p1 if player_id == 1 else view_cut_index_p2
            filtered = []
            guess_prefix = f"{opp_name} が g（予想）→"
            for idx, e in enumerate(actions_log_all):
                if e.startswith(f"{opp_name} ") and (cut is None or idx >= cut):
                    # 予想（g）はすでに上の "相手の予想履歴" で表示するので、ここでは除外
                    if e.startswith(guess_prefix):
                        continue
                    filtered.append(e)
            print("［相手の行動履歴（フル）］")
            if filtered:
                for e in filtered:
                    print(" -", e)
            else:
                print(" - （まだ行動なし）")

        if my_show_panel:
            # 自分のトラップ（A=即負け / B=情報）を自分だけに表示
            if player_id == 1:
                my_kill = sorted(trap1_kill_set)
                my_info = sorted(trap1_info_set)
            else:
                my_kill = sorted(trap2_kill_set)
                my_info = sorted(trap2_info_set)
            if not my_kill and not my_info:
                print("［自分のトラップ］未設定")
            else:
                k_txt = ", ".join(str(x) for x in my_kill) if my_kill else "なし"
                i_txt = ", ".join(str(x) for x in my_info) if my_info else "なし"
                print(f"［自分のトラップ］A即負け=({k_txt}) / B情報=({i_txt})")

        while True:
            suffix = "（使用不可" + ("" if player_id == 1 else "") + ")" if not c_available else ""
            action = input(
                f"{my_name}の行動を選んでください [g=相手の数を当てる / h=ヒントをもらう / c=自分の数を変更{ '（今は使用不可）' if not c_available else ''} / t=トラップを仕掛ける]: "
            ).strip().lower()
            if action in ("g", "h", "c", "t"):
                if action == "c" and not c_available:
                    print("⚠ 今は c は使えません（最近使用したためクールダウン中）。別の行動を選んでください。")
                    continue
                break
            print("⚠ g / h / c / t のいずれかを入力してください。")

        if action == "g":
            # 予想のみ（外れでもヒントは出ない）
            while True:
                try:
                    s = input(f"{my_name}、{opp_name}の秘密の数字を予想して入力してください（{eff_NUM_MIN}〜{eff_NUM_MAX}）: ")
                    guess = int(s)
                    if eff_NUM_MIN <= guess <= eff_NUM_MAX:
                        break
                except ValueError:
                    pass
                print(f"⚠ {eff_NUM_MIN}〜{eff_NUM_MAX}の整数で入力してください。")
            if player_id == 1:
                tries1 += 1
            else:
                tries2 += 1

            # まずは“正解”を最優先：当てたら即勝利（トラップより優先）
            if guess == opponent_secret:
                append_log(f"{my_name} が g（予想）→ {guess}（正解！相手は即死）", player_id)
                winner = player_id
                return

            # 先にトラップ判定（kill=±1即死, ±5スキップ / info）
            opp_kill = trap2_kill_set if player_id == 1 else trap1_kill_set
            opp_info = trap2_info_set if player_id == 1 else trap1_info_set

            # killトラップ：±1 で即死
            if any(abs(guess - k) <= 1 for k in opp_kill):
                append_log(f"{my_name} が g（予想）→ {guess}（killトラップ±1命中＝即敗北）", player_id)
                winner = 2 if player_id == 1 else 1
                print("💥 即負けトラップ（±1）命中！ このラウンドは相手の勝利！")
                return

            # infoトラップ（可視化は“次の自分のターンから”、可視範囲はこの瞬間以降）
            if guess in opp_info:
                if player_id == 1:
                    pending_view_opponent_full_history_p2 = True
                    view_cut_index_p2 = len(actions_log_all)
                else:
                    pending_view_opponent_full_history_p1 = True
                    view_cut_index_p1 = len(actions_log_all)
                print("📜 情報トラップ発動！ 相手は“次の自分のターンから”、この瞬間以降のあなたの行動履歴が見られるようになる。")
                append_log(f"{my_name} が g（予想）→ {guess}（情報トラップ発動）", player_id)
                # 即死ではないので処理は続行

            # killトラップ：±5 で次の自分ターンをスキップ（ただし±1は上で即死済み）
            if any(abs(guess - k) <= 5 for k in opp_kill):
                if player_id == 1:
                    skip_next_turn_p1 = True
                else:
                    skip_next_turn_p2 = True
                append_log(f"{my_name} が g（予想）→ {guess}（kill近接±5命中：次ターンスキップ）", player_id)
                print("⏭ 近接トラップ（±5）に触れた！ 次の自分のターンはスキップされます。")
                # ハズレ処理と二重に出さないため、ここでターン終了
                return

            # 通常のハズレ
            append_log(f"{my_name} が g（予想）→ {guess}（ハズレ）", player_id)
            print("はずれ……！ このターンはここまで。")
            return
        elif action == "h":
            # ヒントを取得：自分で種類指定なら重複OK＆在庫消費なし／ランダムなら在庫消費
            choose_type = False
            # このラウンドの後攻のみ、各ラウンド1回だけ種類指定可
            if player_id == 1 and p1_hint_choice_available:
                while True:
                    ans = input(f"{p1_name} はこのラウンド1回だけヒントの種類を指定できます。指定しますか？ [y/n]: ").strip().lower()
                    if ans in ("y", "n"):
                        break
                    print("⚠ y または n を入力してください。")
                if ans == "y":
                    choose_type = True
            if player_id == 2 and p2_hint_choice_available:
                while True:
                    ans = input(f"{p2_name} はこのラウンド1回だけヒントの種類を指定できます。指定しますか？ [y/n]: ").strip().lower()
                    if ans in ("y", "n"):
                        break
                    print("⚠ y または n を入力してください。")
                if ans == "y":
                    choose_type = True

            if choose_type:
                while True:
                    t = input("ヒントの種類を選んでください [w=和 / s=差 / p=積]: ").strip().lower()
                    mapping = {"w": "和", "s": "差", "p": "積"}
                    if t in mapping:
                        hint_type = mapping[t]
                        if player_id == 1:
                            p1_hint_choice_available = False
                        else:
                            p2_hint_choice_available = False
                        chose_by_user = True
                        break
                    print("⚠ w/s/p のいずれかを入力してください。")
            else:
                # ランダム：在庫消費（在庫なければ出せない）
                my_stock = available_hints_p1 if player_id == 1 else available_hints_p2
                if not my_stock:
                    print("（このラウンドのヒントは出尽くしました）")
                    return
                hint_type = random.choice(my_stock)
                my_stock.remove(hint_type)
                chose_by_user = False

            print("🤔 ヒント！")
            if hint_type == "和":
                val = opponent_secret + hidden_secret
            elif hint_type == "差":
                val = abs(opponent_secret - hidden_secret)
            else:
                val = opponent_secret * hidden_secret
            print(f"  {val}")

            # ログ：数値は常に残す。種類は自分で選んだ時のみ付ける
            if chose_by_user:
                append_log(f"{my_name} が h（ヒント取得）{hint_type}＝{val}", player_id)
            else:
                append_log(f"{my_name} が h（ヒントを取得）＝{val}", player_id)
            return
        elif action == "t":
            # トラップ設定：まず種類を選ぶ（kill=1個、info=複数段階で最大5個固定／編集なし）
            my_secret_now = secret1 if player_id == 1 else secret2
            if player_id == 1:
                my_kill = trap1_kill_set
                my_info = trap1_info_set
            else:
                my_kill = trap2_kill_set
                my_info = trap2_info_set

            # 種類選択（y/n同様に厳密受付）
            while True:
                tkind = input("どのトラップにしますか？ [k=kill（即負け） / i=info（情報）]: ").strip().lower()
                if tkind in ("k", "i"):
                    break
                print("⚠ k または i を入力してください。")

            def read_trap_value(prompt: str) -> int:
                while True:
                    try:
                        s2 = input(prompt)
                        tval = int(s2)
                        if eff_NUM_MIN <= tval <= eff_NUM_MAX:
                            # 自分の秘密の数と同じ値は不可
                            if tval == my_secret_now:
                                print("⚠ 自分の秘密の数と同じ数字はトラップにできません。")
                                continue
                            # マイナス許可時は、絶対値が自分の数と同じ値も不可（例：自分=5 → 5/-5はNG）
                            if allow_negative and abs(tval) == abs(my_secret_now):
                                print("⚠ 負の数ありモードでは、自分の数と絶対値が同じ数字はトラップにできません。")
                                continue
                            return tval
                    except ValueError:
                        pass
                    print(f"⚠ {eff_NUM_MIN}〜{eff_NUM_MAX}の整数で入力してください。")

            if tkind == 'k':
                # kill は各プレイヤー1個まで（再設定＝上書き可）
                tval = read_trap_value("killトラップの数字は何にしますか？: ")
                if len(my_kill) >= 1:
                    old = next(iter(my_kill))
                    my_kill.clear()
                    my_kill.add(tval)
                    cur_k = ", ".join(str(x) for x in sorted(my_kill)) or "なし"
                    cur_i = ", ".join(str(x) for x in sorted(my_info)) or "なし"
                    print(f"［OK］killを上書き：{old} → {tval}。現在：A即負け=({cur_k}) / B情報=({cur_i})")
                    return
                else:
                    my_kill.add(tval)
                    cur_k = ", ".join(str(x) for x in sorted(my_kill)) or "なし"
                    cur_i = ", ".join(str(x) for x in sorted(my_info)) or "なし"
                    print(f"［OK］killを追加。現在：A即負け=({cur_k}) / B情報=({cur_i})")
                    return

            # info は段階的に最大5個まで。編集不可。
            current = len(my_info)
            if current >= 5:
                print("⚠ 情報トラップは既に5個あります。これ以上は追加できません。")
                return

            # 0,1,2個 → 3個目までを埋めるプロンプト / 3,4個 → 5個目まで
            if current < 3:
                start_idx = current + 1
                end_idx = 3
                labels = {1: "一つ目は何にしますか？", 2: "二つ目は？", 3: "三つ目は？"}
                for i in range(start_idx, end_idx + 1):
                    tval = read_trap_value(f"{labels[i]} ")
                    my_info.add(tval)
            else:
                # 3個以上なら、4つ目→5つ目
                labels = {4: "四つ目は？", 5: "五つ目は？"}
                for i in range(current + 1, 6):
                    if len(my_info) >= 5:
                        break
                    tval = read_trap_value(f"{labels[i]} ")
                    my_info.add(tval)

            cur_k = ", ".join(str(x) for x in sorted(my_kill)) or "なし"
            cur_i = ", ".join(str(x) for x in sorted(my_info)) or "なし"
            print(f"［OK］infoを追加。現在：A即負け=({cur_k}) / B情報=({cur_i})")
            return
        else:  # action == "c"
            while True:
                try:
                    s = input(f"{my_name}、自分の秘密の数字を{eff_NUM_MIN}〜{eff_NUM_MAX}で再設定してください: ")
                    new_val = int(s)
                    if eff_NUM_MIN <= new_val <= eff_NUM_MAX:
                        # 自分のトラップ（A/B）いずれかと同じ値には変更できない
                        if player_id == 1:
                            my_all_traps = trap1_kill_set | trap1_info_set
                        else:
                            my_all_traps = trap2_kill_set | trap2_info_set
                        if new_val in my_all_traps:
                            print("⚠ その数字は現在のトラップに含まれています。別の数字を選んでください。")
                            continue
                        if player_id == 1:
                            secret1 = new_val
                        else:
                            secret2 = new_val
                        break
                except ValueError:
                    pass
                print(f"⚠ {eff_NUM_MIN}〜{eff_NUM_MAX}の整数で入力してください。")
            # c 使用後は次の自分の2ターンは使用不可
            if player_id == 1:
                cooldown1 = 2
                # 相手（P2）のヒント在庫をリセット
                available_hints_p2[:] = ["和", "差", "積"]
            else:
                cooldown2 = 2
                # 相手（P1）のヒント在庫をリセット
                available_hints_p1[:] = ["和", "差", "積"]
            append_log(f"{my_name} が c（自分の数を変更）→ {new_val}", player_id)
            return

    # だれかが当てるまで続ける（先行は starter に従う）
    while True:
        if starter == 1:
            # プレイヤー1 → プレイヤー2 の順
            input(f"▶ {p1_name} の番です。{p2_name} は見ないでね！（Enterで続行）")
            clear_screen()
            player_turn(1)
            if winner is not None:
                score1 += 1
                print(f"🎉 ラウンド勝者：{p1_name}！ {tries1}回で当てたよ！")
                print(f"★ 現在のスコア: {p1_name} {score1} - {score2} {p2_name}\n")
                print("このラウンドの行動履歴:")
                for entry in actions_log_all:
                    print(" -", entry)
                # ラウンドの答え（公開）
                print("\n［このラウンドの答え］")
                print(f"  {p1_name} の数: {secret1}")
                print(f"  {p2_name} の数: {secret2}")
                print(f"  誰も知らない数: {hidden_secret}")
                # 次ラウンドは負けた方（=プレイヤー2）が先行
                starter = 2
                input("次のラウンドへ（Enterで画面を隠す）")
                clear_screen()
                break

            input(f"▶ {p2_name} の番です。{p1_name} は見ないでね！（Enterで続行）")
            clear_screen()
            player_turn(2)
            if winner is not None:
                score2 += 1
                print(f"🎉 ラウンド勝者：{p2_name}！ {tries2}回で当てたよ！")
                print(f"★ 現在のスコア: {p1_name} {score1} - {score2} {p2_name}\n")
                print("このラウンドの行動履歴:")
                for entry in actions_log_all:
                    print(" -", entry)
                # ラウンドの答え（公開）
                print("\n［このラウンドの答え］")
                print(f"  {p1_name} の数: {secret1}")
                print(f"  {p2_name} の数: {secret2}")
                print(f"  誰も知らない数: {hidden_secret}")
                # 次ラウンドは負けた方（=プレイヤー1）が先行
                starter = 1
                input("次のラウンドへ（Enterで画面を隠す）")
                clear_screen()
                break
        else:
            # プレイヤー2 → プレイヤー1 の順
            input(f"▶ {p2_name} の番です。{p1_name} は見ないでね！（Enterで続行）")
            clear_screen()
            player_turn(2)
            if winner is not None:
                score2 += 1
                print(f"🎉 ラウンド勝者：{p2_name}！ {tries2}回で当てたよ！")
                print(f"★ 現在のスコア: {p1_name} {score1} - {score2} {p2_name}\n")
                print("このラウンドの行動履歴:")
                for entry in actions_log_all:
                    print(" -", entry)
                # ラウンドの答え（公開）
                print("\n［このラウンドの答え］")
                print(f"  {p1_name} の数: {secret1}")
                print(f"  {p2_name} の数: {secret2}")
                print(f"  誰も知らない数: {hidden_secret}")
                # 次ラウンドは負けた方（=プレイヤー1）が先行
                starter = 1
                input("次のラウンドへ（Enterで画面を隠す）")
                clear_screen()
                break

            input(f"▶ {p1_name} の番です。{p2_name} は見ないでね！（Enterで続行）")
            clear_screen()
            player_turn(1)
            if winner is not None:
                score1 += 1
                print(f"🎉 ラウンド勝者：{p1_name}！ {tries1}回で当てたよ！")
                print(f"★ 現在のスコア: {p1_name} {score1} - {score2} {p2_name}\n")
                print("このラウンドの行動履歴:")
                for entry in actions_log_all:
                    print(" -", entry)
                # ラウンドの答え（公開）
                print("\n［このラウンドの答え］")
                print(f"  {p1_name} の数: {secret1}")
                print(f"  {p2_name} の数: {secret2}")
                print(f"  誰も知らない数: {hidden_secret}")
                # 次ラウンドは負けた方（=プレイヤー2）が先行
                starter = 2
                input("次のラウンドへ（Enterで画面を隠す）")
                clear_screen()
                break

    round_no += 1

# マッチ終了
clear_screen()

if score1 > score2:
    print(f"🏆 マッチ勝者：{p1_name}！ 最終スコア {p1_name} {score1} - {score2} {p2_name}")
else:
    print(f"🏆 マッチ勝者：{p2_name}！ 最終スコア {p1_name} {score1} - {score2} {p2_name}")