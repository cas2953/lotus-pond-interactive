# 荷花池・互動水面

正上方俯視的互動水景。觸碰水面 → 真實高度場漣漪折射整個池面 + 水滴聲 + 魚加速散開。
水面下有隨波搖擺(柔焦)的枝葉、游動的錦鯉;水面上漂著 3D 荷花與浮葉。
背景是**真實水波影片**(無縫 Loop、染成荷塘青綠)再疊一層程式焦散波紋。

水波紋演算法移植自參考專案「聲音漣漪」(Canvas 2D 高度場 + 梯度折射),改為**觸控觸發**。

---

## 檔案結構

```
index.html              主程式(整合 3D 精靈圖 + 影片底圖 + 前台編輯器)
start.bat               本地伺服器啟動器(載入 3D 精靈圖/影片時必須用它開)
tools/render_assets.py  Blender 批次渲染:把 FBX/OBJ/GLB → 俯視透明 PNG
assets/sprites/         Blender 輸出的精靈圖 + manifest.json
assets/video/           無縫 Loop 的水波底圖影片(loop1.mp4 / loop2.mp4)
*.mov(根目錄)         原始素材影片(已壓成 assets/video,部署時用 .gitignore 排除)
model/                  原始 3D 模型來源(僅渲染用,不部署)
```

---

## 執行方式

雙擊 **`start.bat`**(本機伺服器)→ 自動開 <http://localhost:8080/index.html>。

> ⚠️ **必須**透過 `start.bat`(本機伺服器)開啟,不能直接 `file://` 雙擊。
> 水面折射用 `getImageData` 讀像素、底圖用 `<video>`,直接開檔會被瀏覽器安全限制擋下。
> `start.bat` 需要 Python;若沒有,安裝 Python 或改用 VS Code 的 Live Server。

`index.html` 會自動偵測 `assets/sprites/manifest.json`:有就用 3D 精靈圖,沒有就回退到程式繪製。
偵測不到影片(如 file:// 直開)時,底圖自動回退到漸層色。

---

## 前台編輯器(按 `E` 開關)

右側滑入面板,所有設定**自動存於 localStorage**(展場設定一次即記住)。可調:

| 分類 | 項目 |
|---|---|
| 花 | 數量、密度、大小、**傾角(2.5D)**、**光照方向** |
| 葉 | 數量、密度、大小 |
| 魚 | 數量、**巡游速度**、**受驚反應速度**、大小 |
| 水草 | 數量、**水面下模糊** |
| 漣漪/搖晃 | 漣漪強度、搖晃幅度(初始)、搖晃阻尼(持久度)、背景光紋數量 |
| 背景水面 | 程式波紋疊加、影片播放速率、**底圖影片切換**、影片染色、後備底色 |

> 花朵的真實 3D 立體光影是「烘焙」在每張精靈圖上的(見下方多打光渲染);
> 編輯器的「光照方向」是疊在貼圖上的方向性明暗,「傾角」是螢幕空間的 2.5D 壓扁——
> 兩者都是即時近似調整,要改真實 3D 角度/打光請重渲(見下)。

---

## 重新渲染精靈圖(Blender)

```powershell
# 全部重渲(魚 + 睡蓮葉 + 荷花)
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python "tools\render_assets.py"

# 只重渲荷花(其餘沿用既有 manifest,快很多)
& "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python "tools\render_assets.py" -- --only lotus
```

荷花:單朵 GLB → **5 色(粉/白/金/薰衣草/紫)× 3 視角(0° 正俯視 / 4° / 5° 微傾)**,
每個視角搭不同打光(暖側光 / 冷側光 / 柔正光)→ 立體不單調。

## 重做背景影片(ffmpeg,無縫 Loop)

```bash
ffmpeg -i 原始.mov -filter_complex \
"[0:v]scale=1280:720:force_original_aspect_ratio=increase,crop=1280:720,fps=24,setpts=PTS-STARTPTS[v0];\
 [v0]split=3[a][b][c];[a]trim=0:1.2,setpts=PTS-STARTPTS[head];\
 [b]trim=L:D,setpts=PTS-STARTPTS[tail];[c]trim=1.2:L,setpts=PTS-STARTPTS[body];\
 [tail][head]xfade=transition=fade:duration=1.2:offset=0[mix];[mix][body]concat=n=2:v=1[v]" \
 -map "[v]" -an -c:v libx264 -pix_fmt yuv420p -movflags +faststart -crf 26 assets/video/loopX.mp4
# L = 影片長度 - 1.2,D = 影片長度(把尾段 1.2 秒交叉淡接到開頭→首尾無縫)
```

---

## 操作

- 觸碰/點擊水面:泛起漣漪、魚群散開、水滴聲。
- 按 `E`:開關前台編輯器。
- 右上角 🔊:音效開關。
- 自動等比縮放置中,適配任何螢幕/投影(設計座標 2100×900,21:9)。
