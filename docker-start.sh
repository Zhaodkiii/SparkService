#!/bin/bash
set -e

echo "🐳 SparkService Docker 启动脚本"
echo "======================================"

# 检查 Docker 是否运行
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker Desktop 未运行"
    echo "📌 请启动 Docker Desktop 并重试"
    exit 1
fi

echo "✅ Docker 正在运行"

# 检查 docker-compose
if ! command -v docker compose &> /dev/null; then
    echo "❌ docker compose 未找到"
    exit 1
fi

echo "✅ docker compose 可用"

# 构建镜像
echo ""
echo "🔨 构建 Docker 镜像..."
docker build -t sparkservice:latest . || {
    echo "❌ 构建失败 - 检查 Dockerfile 和依赖"
    exit 1
}
echo "✅ 镜像构建成功"

# 启动服务
echo ""
echo "🚀 启动 docker-compose 服务..."
docker compose up --pull always -d || {
    echo "❌ 启动失败"
    echo "💡 如遇 'read-only file system' 错误，请重启 Docker Desktop"
    exit 1
}

echo "✅ 所有服务已启动"

# 等待服务就绪
echo ""
echo "⏳ 等待数据库服务就绪（30秒）..."
sleep 30

# 执行数据库迁移
echo ""
echo "🔄 执行数据库迁移..."
docker compose exec -T app python manage.py migrate || {
    echo "⚠️  迁移失败（可能是数据库尚未完全启动）"
    echo "💡 稍后重试：docker compose exec app python manage.py migrate"
}

# 收集静态文件
echo ""
echo "📦 收集静态文件..."
docker compose exec -T app python manage.py collectstatic --noinput --no-input 2>/dev/null || true

# 显示服务状态
echo ""
echo "======================================"
echo "📊 服务状态："
echo "======================================"
docker compose ps

echo ""
echo "======================================"
echo "✅ 部署完成！"
echo "======================================"
echo ""
echo "🌐 访问地址："
echo "  • API:        http://localhost:8000/"
echo "  • Admin:      http://localhost:8000/admin/"
echo "  • WebSocket:  ws://localhost:8000/ws/"
echo ""
echo "📋 常用命令："
echo "  • 查看日志:    docker compose logs -f app"
echo "  • 进入 shell:  docker compose exec app python manage.py shell"
echo "  • 停止服务:    docker compose down"
echo "  • 完全清理:    docker compose down -v"
echo ""
echo "💡 更多信息请查看 DOCKER_SETUP.md"
