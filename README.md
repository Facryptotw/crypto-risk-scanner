# 如何上傳到 GitHub

## 📁 需要上傳的檔案

請將以下**所有檔案**一起上傳到 GitHub：

1. `index.html` - 主網頁檔案
2. `favicon.ico` - Favicon 圖示（主要）
3. `favicon-16x16.png` - 16x16 PNG 圖示
4. `favicon-32x32.png` - 32x32 PNG 圖示

## 🚀 上傳步驟

### 方法 1：使用 GitHub 網頁介面

1. 登入 GitHub
2. 進入你的儲存庫（Repository）
3. 點擊 "Add file" → "Upload files"
4. **將所有 4 個檔案一起拖曳**到上傳區域
5. 填寫 Commit message（例如：「Add favicon」）
6. 點擊 "Commit changes"

### 方法 2：使用 Git 指令

```bash
git add index.html favicon.ico favicon-16x16.png favicon-32x32.png
git commit -m "Add website with favicon"
git push
```

## ⚠️ 重要提醒

- **所有 favicon 檔案必須和 index.html 放在同一個目錄**
- 上傳後可能需要等幾分鐘才會生效
- 如果還是看不到圖示，請**清除瀏覽器快取**：
  - Chrome/Edge: `Ctrl + Shift + Delete` 或 `Cmd + Shift + Delete`
  - 勾選「快取的圖片和檔案」
  - 點擊「清除資料」

## 🌐 GitHub Pages 設定（如果需要）

如果你想使用 GitHub Pages 來架設網站：

1. 進入儲存庫的 Settings
2. 點擊左側的 "Pages"
3. 在 "Source" 選擇 "main" 分支
4. 點擊 "Save"
5. 網站會發布在：`https://你的帳號.github.io/儲存庫名稱/`

## ✅ 檢查是否成功

上傳成功後，訪問你的網站，favicon 應該會顯示在：
- 瀏覽器標籤頁
- 書籤列
- 歷史記錄
