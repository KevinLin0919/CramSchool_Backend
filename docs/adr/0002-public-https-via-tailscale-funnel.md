# 用 Tailscale Funnel 對外，不要求老師裝 VPN

伺服器放在補習班的機器上，以 Tailscale Funnel 提供一個公開的 HTTPS 網址，App 預設就連這個網址，在補習班、在家都能用，老師不必裝 Tailscale。另外保留補習班內網位址，給對外網路斷線時使用。代價：Funnel 會經過 Tailscale 的中繼伺服器，有官方說明的頻寬限制；實測外部下載偶爾會卡 20–30 秒，有開 Tailscale 的裝置會自動走內網而比較快。若之後要換成網域加其他通道，App 只需要改預設網址。
