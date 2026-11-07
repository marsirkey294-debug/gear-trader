# ギアトレイダー（Gear Trader）

円安を利用して、日本の商品を海外で売り、利益を出すための検討チームです。まずは中古ゴルフギア（ドライバーヘッド、日本仕様シャフト、地クラブなど）をeBayで小さく試し、実績が出たら他の海外サイトへ、運営が軌道に乗ったら他の日本の商品へ広げます。

チーム（為替担当と5つの部隊）が行うのは、調査・計算・提案・報告書づくりまでです。仕入れ・出品・支払いなど、お金が動く決定はオーナーが行います。

- 計画書（Claude Docs）：https://claude.ai/artifact/J9BXiA81QtBGz3w1AWtb8M
- 毎朝7時45分：定期実行タスク「ギアトレイダー 為替チェック」がレートと撤退ラインの段階を通知

## 中身

| パス | 内容 |
| --- | --- |
| `skill/SKILL.md` | スキル本体（最終目的、手順、相談の大きさに合わせた使い分け） |
| `skill/references/rules.md` | 計算の前提、相場の出し方、取引スコア、ゲート、撤退ライン、在庫、関税、商品カテゴリの拡大 |
| `skill/references/teams.md` | 為替担当と5つの部隊への指示 |
| `skill/scripts/profit_calc.py` | 相場（落札価格の中央値）、利益、為替シナリオ、悪いケース、取引スコアの計算 |
| `simulation/` | PINGの価格差シミュレーション（Excel）と、計算スクリプトの入力例 |

## 計算スクリプトの使い方

```bash
python skill/scripts/profit_calc.py --rate 155 --avg30 153 \
  --items simulation/items_example.json --scenarios 140,165
```

`items_example.json` の数値は動作確認用の例です。一部に出品価格が混ざっているため、実際の判断には使わないでください。

## GitHubの公開事例から取り入れた方法

| 方法 | 参考にしたリポジトリ |
| --- | --- |
| 相場は「同じ商品の落札価格の中央値」。外れ値は四分位範囲（IQR）で除く。3件未満は「データ不足」 | dnadeau/sports-card-manager、cyberkirbi/bb-ebay-arbitrage |
| 違う市場（ヘッドのみと完成品など）を混ぜず、一致しない出品は除外する | dnadeau/sports-card-manager |
| 利益だけでなく、悪いケースの損失で減点する取引スコア（買い候補／様子見／見送り） | Arshiaheravi/autoflip |
| 売れる速さと値動きの大きさを見る、ウォッチリストで値下がりを待つ | BlekSoft/MarketDelta-Ebay-Arbitrage-Engine、Arshiaheravi/autoflip |
| eBayのデータは公式APIか、サインインしたブラウザで見る（自動読み取りは利用規約違反） | dnadeau/sports-card-manager |
| 為替と関税まで含めた利益計算 | emijuri0514-gif/mercari-ebay-lister |
| 指摘に重さを付け、重大な指摘が残る限り合格にしない。直らなければオーナーに上げる | alirezarezvani/claude-skills（human-gate） |
| 部隊は自分が判定される基準を変えない。台帳で前回から再開する | alirezarezvani/claude-skills（agent-harness） |
| 予想と実績の答え合わせで、ルールを根拠付きで見直す | alirezarezvani/claude-skills（skill-retro） |

## スキルとして使う

`skill/` フォルダをスキルとして登録すると、「部隊を動かして」や仕入れ・相場・為替の相談で使われます。
