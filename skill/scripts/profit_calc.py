#!/usr/bin/env python3
"""ギアトレイダー 利益計算スクリプト（v2）

全部隊が同じ式で計算するための共通ツール。部隊ごとに計算がずれると、
吟味部隊の検証も判断部隊の合否も意味がなくなるため、利益の数字は必ずこれで出す。

v2で取り入れた方法（GitHubの公開事例から）:
- 相場は「落札価格の中央値」。外れ値は四分位範囲（IQR）で除く
  （sports-card-manager / bb-ebay-arbitrage と同じやり方）
- 一致した落札が3件未満なら、価格ではなく「データ不足」と表示する
- 落札価格がなければ出品価格×0.8で代用するが、確度は「低」にする
- 値動きの大きさ（ばらつき）と、最悪ケースの損失で減点する取引スコア
  （autoflip の BUY / WATCH / SKIP 方式）

使い方:
  python profit_calc.py --rate 155 --avg30 153 --items items.json [--scenarios 145,155,165]

items.json の例（配列）:
  [
    {"name": "G440 LST ヘッド", "cost_jpy": 44000, "kind": "head",
     "sold_usd": [391, 440, 469, 455, 430]},
    {"name": "G430 10K ヘッド", "cost_jpy": 26300, "kind": "head", "price_usd": 300},
    {"name": "三浦技研 TB-ZERO", "cost_jpy": 109800, "kind": "iron_set", "asking_usd": [1232]}
  ]

価格の指定（優先順）:
  sold_usd   : 一致した落札価格のリスト（最も信頼できる）
  price_usd  : すでに決めた相場（出典は別に記録すること）
  asking_usd : 出品価格のリスト（中央値×0.8で代用。確度は低）
kind: head / shaft / club / iron_set （送料と梱包が変わる）
tax_refund: 課税事業者から仕入れて消費税還付を受けられる場合だけ true
"""
import argparse
import json
import statistics
import sys

FEE_RATE = 0.15      # eBay手数料（落札手数料＋海外取引手数料）の目安
FX_FEE_RATE = 0.02   # 為替・入金手数料の目安
NET = 1 - FEE_RATE - FX_FEE_RATE  # = 0.83
SHIPPING = {"head": 4000, "shaft": 6000, "club": 7000, "iron_set": 10000}
PACKING = {"head": 500, "shaft": 500, "club": 500, "iron_set": 1000}
TARGET = 0.15        # 仕入れ候補にする利益率
FLOOR_5YEN = 0.10    # 5円円高でも残すべき利益率
MIN_COMPS = 3        # これ未満の落札件数では相場とみなさない
ASKING_DISCOUNT = 0.8  # 出品価格しかないときの割引（出品価格は売れた値段ではないため）


def stage(avg30: float) -> str:
    """撤退ラインの段階（30日平均で判断する。一日のレートで振り回されないため）"""
    if avg30 >= 150:
        return "150円以上：通常どおり"
    if avg30 >= 145:
        return "145〜150円：利益率15%を割る商品の仕入れを止める"
    if avg30 >= 135:
        return "135〜145円：仕入れを減らし、在庫の上限を半分にする"
    if avg30 >= 125:
        return "135円未満：新しい仕入れを止める（撤退）。在庫は売り切る"
    return "125円未満：全商品がほぼ赤字。在庫の売り切りを急ぐ"


def iqr_filter(xs):
    """四分位範囲（IQR）の1.5倍から外れた値を除く。件数が少ないときは何もしない"""
    if len(xs) < 4:
        return list(xs)
    q = statistics.quantiles(xs, n=4)
    lo, hi = q[0] - 1.5 * (q[2] - q[0]), q[2] + 1.5 * (q[2] - q[0])
    return [x for x in xs if lo <= x <= hi]


def market(item: dict) -> dict:
    """相場（ドル）、確度、件数、ばらつき を決める"""
    sold = [float(x) for x in item.get("sold_usd", [])]
    if sold:
        kept = iqr_filter(sold)
        n = len(kept)
        med = statistics.median(kept)
        spread = (max(kept) - min(kept)) / med if n >= 2 else 0.0
        if n < MIN_COMPS:
            return {"usd": med, "conf": "データ不足", "n": n, "spread": spread, "basis": "落札"}
        conf = "高" if n >= 8 else "中"
        return {"usd": med, "conf": conf, "n": n, "spread": spread, "basis": "落札"}
    if "price_usd" in item:
        return {"usd": float(item["price_usd"]), "conf": item.get("conf", "中"), "n": None,
                "spread": float(item.get("spread", 0.2)), "basis": "指定"}
    ask = [float(x) for x in item.get("asking_usd", [])]
    if ask:
        med = statistics.median(iqr_filter(ask))
        return {"usd": med * ASKING_DISCOUNT, "conf": "低", "n": len(ask), "spread": 0.3,
                "basis": f"出品×{ASKING_DISCOUNT}"}
    raise ValueError(f"{item.get('name')}: sold_usd / price_usd / asking_usd のどれかが必要です")


def profit(item: dict, usd: float, rate: float) -> tuple:
    kind = item.get("kind", "head")
    cost = float(item["cost_jpy"])
    refund = cost * 10 / 110 if item.get("tax_refund") else 0.0
    p = usd * rate * NET - SHIPPING[kind] - PACKING[kind] - cost + refund
    return p, (p / cost if cost else 0.0)


def breakeven(item: dict, usd: float, margin: float) -> float:
    kind = item.get("kind", "head")
    cost = float(item["cost_jpy"])
    refund = cost * 10 / 110 if item.get("tax_refund") else 0.0
    return (cost * (1 + margin) + SHIPPING[kind] + PACKING[kind] - refund) / (usd * NET)


def score(m_now: float, m_worst: float, worst_profit: float, cost: float, conf: str) -> tuple:
    """取引スコア（1〜10）と判定。利益率を土台に、悪いケースと確度で減点する"""
    s = 5 + round((m_now - TARGET) * 20)          # 15%で5点、20%で6点、10%で4点
    if m_worst < 0:
        s -= 2                                      # 悪いケースで赤字
    elif m_worst < FLOOR_5YEN:
        s -= 1
    if worst_profit < -0.1 * cost:
        s -= 1                                      # 悪いケースの損失が仕入れ値の1割超
    if conf == "低":
        s -= 1
    s = max(1, min(10, s))
    if conf == "データ不足":
        return s, "見送り（データ不足）"
    if s >= 7 and m_now >= TARGET:
        return s, "買い候補"
    if s >= 4:
        return s, "様子見"
    return s, "見送り"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--rate", type=float, required=True, help="当日のドル円")
    p.add_argument("--avg30", type=float, help="直近30日平均のドル円（撤退ラインの判定用）")
    p.add_argument("--items", required=True, help="商品リストのJSONファイル")
    p.add_argument("--scenarios", default="", help="為替シナリオのレート（カンマ区切り）")
    a = p.parse_args()

    with open(a.items, encoding="utf-8") as f:
        items = json.load(f)
    scen = [float(x) for x in a.scenarios.split(",") if x.strip()]

    out = []
    if a.avg30:
        out.append(f"撤退ラインの段階（30日平均 {a.avg30:.1f}円）：{stage(a.avg30)}\n")
    head = ["商品", "相場USD（根拠・件数・確度）", f"利益（{a.rate:.0f}円）", "利益率", "5円円高", "10円円高"]
    head += [f"{r:.0f}円" for r in scen]
    head += ["悪いケース", "分岐点", "15%の為替", "スコア", "判定"]
    out.append("| " + " | ".join(head) + " |")
    out.append("|" + " --- |" * len(head))
    for it in items:
        mk = market(it)
        usd, cost = mk["usd"], float(it["cost_jpy"])
        pr, m = profit(it, usd, a.rate)
        _, m5 = profit(it, usd, a.rate - 5)
        _, m10 = profit(it, usd, a.rate - 10)
        # 悪いケース：10円円高 かつ 相場がばらつきの半分だけ下振れ
        worst_usd = usd * (1 - min(mk["spread"], 0.6) / 2)
        wp, wm = profit(it, worst_usd, a.rate - 10)
        sc, label = score(m, wm, wp, cost, mk["conf"])
        n = "" if mk["n"] is None else f"{mk['n']}件・"
        row = [it["name"], f"{usd:,.0f}（{mk['basis']}・{n}{mk['conf']}）", f"{pr:,.0f}円", f"{m:.1%}",
               f"{m5:.1%}", f"{m10:.1%}"]
        row += [f"{profit(it, usd, r)[1]:.1%}" for r in scen]
        row += [f"{wm:.1%}", f"{breakeven(it, usd, 0):.0f}円", f"{breakeven(it, usd, TARGET):.0f}円",
                f"{sc}", label]
        out.append("| " + " | ".join(row) + " |")
    out.append(
        f"\n前提：手数料合計{FEE_RATE + FX_FEE_RATE:.0%}、送料・梱包は種類別の目安。"
        "利益率＝利益÷仕入れ値。悪いケース＝10円円高かつ相場がばらつきの半分だけ下がった場合。"
        f"相場は落札価格の中央値（IQRで外れ値除外）。落札{MIN_COMPS}件未満は「データ不足」。"
        "買い候補＝スコア7以上かつ当日15%以上。")
    sys.stdout.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
