# 部署说明

## 当前部署(Lightsail · 13.193.30.180)

- 代码位置:服务器 `~/aichat`(git clone,main 分支)
- 运行方式:`~/aichat/deploy` 下 `docker compose up -d`(postgres:16 + 服务端;迁移、管理员引导在容器启动命令内自动执行)
- 对外入口:`http://13.193.30.180/aichat`(实例防火墙只放行 22/80,API 经本机 Caddy `/aichat/*` 路径反代到容器 8000 端口;REST 与 WSS 均验证可达)
- 密钥:全部在服务器 `~/aichat/deploy/.env`(权限 600),含 `POSTGRES_PASSWORD`、`AICHAT_JWT_SECRET`、`AICHAT_CREDENTIAL_MASTER_KEY`(Fernet)、`ADMIN_BOOTSTRAP_PASSWORD`
- 移动端配置:服务器地址填 `http://13.193.30.180/aichat`

## 首次部署步骤(新机器)

```bash
git clone https://github.com/BugYuan64/AIChat.git ~/aichat
cd ~/aichat/deploy
umask 077
cat > .env <<EOF
POSTGRES_PASSWORD=$(openssl rand -hex 16)
AICHAT_JWT_SECRET=$(openssl rand -hex 32)
AICHAT_CREDENTIAL_MASTER_KEY=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
ADMIN_BOOTSTRAP_PASSWORD=$(openssl rand -hex 8)
AICHAT_BIND=127.0.0.1        # 直连暴露改 0.0.0.0;推荐保持 127.0.0.1 由反代/TLS 暴露
EOF
sudo docker compose up -d --build
```

反代(Caddy 80 端口路径反代示例,`/etc/caddy/Caddyfile` 的 `:80` 站点内):

```caddyfile
handle_path /aichat/* {
    reverse_proxy 127.0.0.1:8000
}
```

注意:该机器 Caddy 由 xray-mihomo-deployer 管理,主配置若被其重写,需重新加入此片段(备份在同目录 `Caddyfile.bak-aichat`)。

## 日常运维

```bash
cd ~/aichat/deploy
sudo docker compose logs -f server        # 看日志
sudo docker compose restart server        # 重启(幂等,管理员已存在则跳过引导)
cd ~/aichat && git pull && cd deploy && sudo docker compose up -d --build   # 更新版本
sudo docker compose exec postgres pg_dump -U aichat aichat > backup.sql      # 备份(另需单独备份 .env 中的主密钥)
```

## 安全提醒

- 当前入口为明文 HTTP(80)。正式使用建议:域名 + Caddy 自动 TLS,或 Lightsail 防火墙放行 443 后启用 HTTPS;密钥与凭据不入库、不进聊天记录。
- `ADMIN_BOOTSTRAP_PASSWORD` 首次登录后即持有管理员会话,请妥善保管并尽快修改部署时生成的随机值。
