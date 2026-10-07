# Domain Docs

兩個 repo，一份共用的用語表。

## Before exploring, read these

- 後端 repo 根目錄的 **`CONTEXT.md`**：全系統共用的用語（模板、母卷、格、待確認、角色…）。在 iOS repo 工作時讀 `../CramSchool_Backend/CONTEXT.md`。
- **`docs/adr/`**：
  - 後端 repo 的 `docs/adr/`：系統層級的決策（環境分離、對外連線、角色）。
  - iOS repo 的 `docs/adr/`：App 內部的決策（對位、辨識、畫面行為）。
  要動哪一塊，就讀那一塊相關的 ADR。

檔案不存在就直接往下做，不必提醒使用者補。

## Use the glossary's vocabulary

產出裡提到領域概念（issue 標題、提案、測試名稱、給使用者的說明）時，用 `CONTEXT.md` 定義的詞，不要換成它列在 _Avoid_ 底下的說法。對使用者說話一律用中文的那個詞。

缺詞的時候，代表你在發明專案沒在用的說法（重新想想），或是真的有缺口（交給 `/domain-modeling` 補）。

## Flag ADR conflicts

產出和既有 ADR 衝突時，明講出來，不要默默推翻：

> _和 ADR-0004（模板只由模板管理者維護）衝突，但值得重新討論，因為…_
