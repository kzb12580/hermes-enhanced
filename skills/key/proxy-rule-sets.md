---
name: proxy-rule-sets
description: Create and maintain China-optimized proxy rule sets for sing-box, Clash (mihomo), and V2Ray/Xray. Includes DNS split, WebRTC leak prevention, fake-ip filtering, and GitHub Actions auto-update.
category: devops
triggers:
  - proxy rules
  - China optimization
  - GFW rules
  - clash rules
  - sing-box rules
  - DNS split
  - WebRTC leak prevention
  - fake-ip
  - 分流规则
  - 国内直连
---

# Proxy Rule Sets Engineering

Create comprehensive, multi-format proxy rule sets optimized for China users. Supports sing-box, Clash (mihomo), and V2Ray/Xray clients with DNS optimization and WebRTC leak prevention.

## Rule Set Architecture

### Three Core Rule Categories

1. **GFW Domains** — Blocked sites that MUST go through proxy
   - Google, YouTube, Facebook, Twitter, Instagram, Reddit
   - Telegram, Discord, Signal
   - Wikipedia, GitHub, Medium
   - AI services (OpenAI, Anthropic, Claude, Gemini)
   - Streaming (Netflix, Disney+, Spotify, Twitch)

2. **China Domains** — Domestic sites that MUST go direct
   - BAT (Baidu, Alibaba, Tencent)
   - Video (Bilibili, iQiyi, Youku, Douyin)
   - E-commerce (JD, Taobao, Pinduoduo, Meituan)
   - Social (Weibo, Zhihu, Xiaohongshu)
   - Finance (banks, Alipay, WeChat Pay)
   - Government/Education (.gov.cn, .edu.cn)

3. **China IPs** — APNIC-assigned China IP ranges (direct)
   - Complete China IP CIDR blocks from APNIC
   - Private IPs (10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16)

### DNS Split Strategy

```
Domain Type → DNS Server → Resolution Path
─────────────────────────────────────────
China domain → 223.5.5.5 (AliDNS) → Direct
GFW domain → 1.1.1.1 via proxy → Proxy
Other → 1.1.1.1 via proxy → Proxy (safe default)
```

**DNS Servers:**
- China: `223.5.5.5` (AliDNS), `119.29.29.29` (Tencent DNS), `doh.pub`
- Proxy: `1.1.1.1` (Cloudflare), `8.8.8.8` (Google), `dns.cloudflare.com/dns-query`

**Fake-IP Mode:**
- Range: `198.18.0.0/15` (IPv4), `fc00::/18` (IPv6)
- Avoids DNS leaks by returning fake IPs for proxied domains
- Mihomo/Clash handles the actual resolution through proxy

### WebRTC Leak Prevention

STUN/TURN requests can bypass proxy and reveal real IP. Block via:

1. **fake-ip-filter** — Add STUN domains to return real IP (not fake):
```javascript
'stun.*.*', 'stun.*.*.*', '+.stun.*.*', '+.stun.*.*.*',
'+.stun.*.*.*.*', '+.stun.*.*.*.*.*',
'lens.l.google.com', '*.n.n.srv.nintendo.net',
'+.xboxlive.com', '*.msftncsi.com', '*.msftconnecttest.com',
'msftconnecttest.com', 'msftncsi.com', 'www.msftconnecttest.com',
'www.msftncsi.com', 'teredo.*', '*.xboxlive.com',
'xbox.*.*.microsoft.com', '+.xboxlive.com',
'speedtest.cros.wr.pvp.net'
```

2. **Rules** — Block STUN/TURN traffic:
```yaml
- DOMAIN-SUFFIX,stun.l.google.com,REJECT
- DOMAIN-KEYWORD,stun,REJECT
- DOMAIN-KEYWORD,turn,REJECT
```

3. **Browser-level** (user action):
   - Chrome: `chrome://flags/#disable-webrtc`
   - Firefox: `about:config` → `media.peerconnection.enabled` → `false`
   - Edge: `edge://flags/#disable-webrtc`

## Multi-Format Output

### sing-box Rule-Set Source (JSON)

```json
{
  "version": 2,
  "rules": [
    {
      "domain_suffix": [".google.com", ".youtube.com", ".facebook.com"]
    }
  ]
}
```

Files:
- `gfw-domains.json` — Proxy domains
- `geosite-cn.json` — China direct domains
- `geosite-geolocation-!cn.json` — Non-China domains
- `geoip-cn.json` — China IP CIDR blocks

### Clash Rule-Provider (YAML)

```yaml
payload:
  - '.google.com'
  - '.youtube.com'
  - '.facebook.com'
```

Files:
- `gfw-domains.yaml` — behavior: domain
- `china-domains.yaml` — behavior: domain
- `china-ips.yaml` — behavior: ipcidr

### V2Ray/Xray Routing (JSON)

Uses `domain` and `ip` arrays in routing rules with `geosite:cn` and `geoip:cn` format.

## GitHub Actions Auto-Update

Create `.github/workflows/update-rules.yml`:

```yaml
name: Update Rules
on:
  schedule:
    - cron: '0 2 * * *'  # Daily UTC 2:00 (Beijing 10:00)
  workflow_dispatch:

jobs:
  update:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Download GFW list
        run: curl -sL "https://raw.githubusercontent.com/gfwlist/gfwlist/master/gfwlist.txt" | base64 -d > /tmp/gfwlist.txt
      - name: Download China domains
        run: curl -sL "https://raw.githubusercontent.com/felixonmars/dnsmasq-china-list/master/accelerated-domains.china.conf" -o /tmp/china-domains-raw.txt
      - name: Download China IPs
        run: curl -sL "https://raw.githubusercontent.com/misakaio/chnroutes2/master/chnroutes.txt" -o /tmp/china-ips-raw.txt
      - name: Process rules
        run: python3 scripts/process_rules.py
      - name: Commit and push
        run: |
          git config user.name "github-actions[bot]"
          git add -A
          git diff --cached --quiet || git commit -m "chore: auto-update rules $(date +%Y-%m-%d)"
          git push
```

## Repository Structure

```
china-proxy-rules/
├── README.md                    # Documentation (Chinese)
├── .github/workflows/
│   └── update-rules.yml         # Auto-update workflow
├── scripts/
│   └── process_rules.py         # Rule processing script
├── rules/
│   ├── gfw-domains.txt          # Source: GFW blocked domains
│   ├── china-domains.txt        # Source: China direct domains
│   ├── china-ips.txt            # Source: China IP ranges
│   ├── singbox/                 # sing-box rule-set sources
│   │   ├── gfw-domains.json
│   │   ├── geosite-cn.json
│   │   ├── geosite-geolocation-!cn.json
│   │   └── geoip-cn.json
│   ├── clash/                   # Clash rule-providers
│   │   ├── gfw-domains.yaml
│   │   ├── china-domains.yaml
│   │   └── china-ips.yaml
│   └── v2ray/                   # V2Ray rules
└── subscription/                # Full config templates
    ├── singbox.json
    ├── clash.yaml
    └── v2ray.json
```

## Data Sources

| Source | URL | Content |
|--------|-----|---------|
| gfwlist | github.com/gfwlist/gfwlist | Blocked domains (base64) |
| dnsmasq-china-list | felixonmars/dnsmasq-china-list | China domains |
| chnroutes2 | misakaio/chnroutes2 | China IP CIDR |
| v2fly/domain-list-community | v2fly/domain-list-community | Community domain list |

## Key Rules

1. **Always use `.` prefix for domain_suffix** — `.google.com` matches all subdomains
2. **Private IPs always direct** — Never proxy 10.x, 172.16-31.x, 192.168.x
3. **Fake-IP for proxied domains** — Avoids DNS leaks
4. **China DNS for China domains** — Direct resolution, faster
5. **Proxy DNS for GFW domains** — Avoid DNS pollution
6. **Default to proxy for unknown** — Safer than direct for GFW users

## Pitfalls

- **sing-box 1.12+**: Legacy DNS servers deprecated, must use `udp://` prefix for plain IP DNS
- **Clash rule-providers**: Must specify `behavior: domain` or `behavior: ipcidr` correctly
- **GFW list format**: Base64 encoded, needs `base64 -d` before processing
- **China IP ranges**: APNIC data changes, needs regular auto-update
- **WebRTC**: Blocking all STUN may break video calls — use fake-ip-filter instead of REJECT for critical services
- **Terminal CWD**: Deleting CWD breaks terminal — see `references/terminal-cwd-pitfall.md` for workaround
