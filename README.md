# 設計図素材変換ツール

Litematica の設計図(`.litematic`)を読み込み、**ジャングル等の木材・色付きガラス・色付きの装飾ブロック**を、
入手しやすい**一般的な素材（オーク・普通のガラス・白/無地）**へ自動で置き換えて、新しいファイルを生成します。

- ファイル選択 or **ドラッグ&ドロップ**で読み込み
- 素材を **マイクラ風の立体アイコン**＋**日本語名**（英語IDも併記）で一覧表示
- **置き換えできる素材／できない素材** の両方を表示（機能ブロック等は「置き換え不可」として保持）
- 置き換え先が気に入らなければ **クリックして候補から選び直し**（画像つき・入手しやすい順）
- **対象バージョンを選択可能**（約5年分を同梱・設計図の DataVersion から自動判定）
- **ライト／ダークのテーマ切替**（右上のボタン）
- 「開始」で **元ファイルはそのまま**、別名で新しい`.litematic`を出力

> ブロックの状態（向き・水没など）、看板の文字やチェストの中身（タイルエンティティ）はそのまま保持されます。
> 内部的には各リージョンの「パレット」の名前だけを書き換えるため、配置は1ブロックも変わりません。

## 自動で置き換える素材（全素材対応）

ゲーム本体の**実際のブロック一覧（26.2 / 全1198種）**を基準に、「同じ形で素材だけ違うブロック」を
グループ化し、**入手しやすい素材ほど上位**に提案します。既定の置き換え先は各グループで**最も入手しやすいもの**。

| 種類 | 変換元（例） | 既定の変換先（最易） |
|------|------------|------------|
| 木材 | spruce / birch / jungle / acacia / dark_oak / mangrove / cherry / pale_oak / bamboo / crimson / warped の planks・stairs・slab・fence・fence_gate・door・trapdoor・log・sign・leaves 等 | オーク(oak) |
| 石系 | 階段・ハーフ・塀・フルブロック全般（stone_brick / granite / diorite / andesite / deepslate / tuff / sandstone / blackstone / quartz / prismarine / purpur / nether_brick … polished/chiseled/cracked 含む） | 丸石(cobblestone) |
| 銅 | 酸化（exposed/weathered/oxidized）・蝋引き（waxed）の各種 cut_copper・copper_block・door・bulb・grate・chest 等 | 素の銅（非酸化・非蝋引き） |
| ガラス | 16色の stained_glass / stained_glass_pane / tinted_glass | 普通の glass / glass_pane |
| 色付き装飾 | 16色の wool・carpet・bed・concrete・concrete_powder・terracotta・glazed_terracotta・candle・shulker_box・banner | 白(white) または無地 |
| 光源 | froglight 3色 | ochre |

- **候補は入手難易度の低い順**に並びます（石系なら 丸石 → 石 → 安山岩… の順）。
- 各グループで既に最も入手しやすいブロック（例: cobblestone、oak_planks、glass）は変換対象になりません。
- 機能ブロック（水・溶岩・ソウルサンド・ホッパー・チェスト・かまど・**丸石の塀** 等）は**自動では変換しません**。
- 置き換え先をクリックすれば、同じ形で使える素材の候補（画像付き・難易度順）から選び直せます。

> 変換先は実在するブロックIDのみを使うため、設計図が壊れることはありません（無効ID生成 0 件を全バージョンで検証済み）。
> アイコンは Mojang のテクスチャを使わず、本ツールが素材ごとのドット模様を自前生成し、
> マイクラのインベントリ風の立体ブロックとして描いた近似画像です（公式アセットは未使用）。

## 対象バージョン（約5年分を同梱）

画面上部の「対象バージョン」で切り替えできます。設計図を読み込むと、その `DataVersion` から**自動で最適なバージョンを選択**します（手動変更も可）。同梱しているレジストリ:

`1.18.2(=1.17.1相当)` / `1.19.4` / `1.20.1` / `1.21.1` / `1.21.3` / `1.21.4` / `1.21.5` / `1.21.8` / `1.21.11` / `26.1.2` / `26.2`

- バージョンによって存在するブロックが違う（例: `tuff_*` は 1.21〜、`cinnabar_*` は 26.2）ため、選んだバージョンに**実在する素材だけ**を候補に出します。
- 同梱外のバージョンに対応したいときは、そのバージョンの jar から作ったブロック一覧を `data\blocks_<版>.txt` として置き、`data\versions.json` に1行追記すれば認識します（`_build_registries.py` で再生成も可能）。

## 使い方（exe を作る）

1. [Python 3.10 以上](https://www.python.org/) をインストール（インストール時に「Add Python to PATH」にチェック）
2. このフォルダの **`build.bat` をダブルクリック**
3. `dist\設計図素材変換ツール.exe` が出来上がります
4. exe をダブルクリックで起動、または exe に `.litematic` を**ドラッグ&ドロップ**

## 配布用インストーラー

配布するときは **`dist\設計図素材変換ツール_Setup.exe`** を渡してください。

インストーラーは管理者権限なしで、ユーザー領域にアプリをインストールします。

- インストール先: `%LOCALAPPDATA%\Programs\SchematicMaterialConverter`
- デスクトップとスタートメニューにショートカットを作成
- Windows の「アプリと機能」からアンインストール可能
- 赤黒の専用インストール画面で、約20秒かけて進行度を表示

インストーラーを作り直す場合:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build-installer.ps1
```

動画つきにしたい場合は、権利のある動画ファイルを **`installer_video.mp4`** という名前で
`設計図素材変換ツール_Setup.exe` と同じフォルダに置いてください。インストール画面内で音ありループ再生を試みます。

## 使い方（exe を作らず、その場で動かす）

```bat
pip install -r requirements.txt
python app.py
```

## ファイル構成

| ファイル | 役割 |
|---------|------|
| `app.py` | GUI 本体 |
| `converter.py` | `.litematic` の読み書き・変換処理 |
| `blockdata.py` | 素材/形の定義・変換ルール・候補 |
| `icons.py` | ブロックアイコンの自動生成（Pillow） |
| `data/blocks_26.2.txt` | 有効ブロックID一覧（変換先の検証に使用・exeに同梱） |
| `build.bat` | exe をビルドするスクリプト |
| `requirements.txt` | 依存ライブラリ |

> 別バージョンに対応させたい場合は、そのバージョンのブロック一覧を `data/blocks_<版>.txt`（1行1ID）として置けば自動で読み込みます。

## 動作環境

- Windows 10 / 11
- 対象フォーマット: Litematica `.litematic`（Minecraft 26.2 / DataVersion 4671 の設計図で確認。1.21系の設計図でも動作します）
