#!/bin/bash
# SparkService Docker 快速参考
# 运行方式: bash docker-quickref.sh <command>

case "$1" in
    "start")
        echo "🚀 启动服务..."
        docker compose up -d
        echo "✅ 服务已启动"
        docker compose ps
        ;;
    "stop")
        echo "🛑 停止服务..."
        docker compose down
        echo "✅ 服务已停止"
        ;;
    "logs")
        docker compose logs -f "${2:-app}"
        ;;
    "shell")
        docker compose exec app python manage.py shell
        ;;
    "migrate")
        echo "🔄 执行数据库迁移..."
        docker compose exec app python manage.py migrate
        ;;
    "createsuperuser")
        echo "👤 创建超级用户..."
        docker compose exec app python manage.py createsuperuser
        ;;
    "collectstatic")
        echo "📦 收集静态文件..."
        docker compose exec app python manage.py collectstatic --noinput
        ;;
    "mysql")
        docker compose exec mysql mysql -u root -p -D sparkservice
        ;;
    "redis-cli")
        docker compose exec redis redis-cli
        ;;
    "clean")
        echo "🧹 清理所有容器和卷..."
        read -p "确定吗？(y/N) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            docker compose down -v
            echo "✅ 清理完成"
        fi
        ;;
    "rebuild")
        echo "🔨 重新构建镜像..."
        docker build -t sparkservice:latest .
        echo "✅ 构建完成，运行 'bash docker-quickref.sh start' 重启"
        ;;
    "status")
        docker compose ps
        ;;
    "health")
        echo "🏥 健康检查..."
        docker compose ps --format "table {{.Service}}\t{{.Status}}"
        echo ""
        echo "容器日志摘要："
        for service in app mysql redis celery_worker celery_beat; do
            echo ""
            echo "--- $service ---"
            docker compose logs --tail 3 $service 2>/dev/null || true
        done
        ;;
    *)
        cat << 'EOF'
SparkService Docker 快速参考
=============================

用法: bash docker-quickref.sh <command>

命令:
  start              启动所有服务
  stop               停止所有服务
  logs [SERVICE]     查看日志 (默认 app)
  shell              进入 Django shell
  migrate            执行数据库迁移
  createsuperuser    创建超级用户
  collectstatic      收集静态文件
  mysql              连接 MySQL
  redis-cli          连接 Redis CLI
  rebuild            重新构建镜像
  status             查看服务状态
  health             完整健康检查
  clean              删除所有容器和卷

示例:
  bash docker-quickref.sh start
  bash docker-quickref.sh logs celery_worker
  bash docker-quickref.sh migrate
EOF
        ;;
esac
