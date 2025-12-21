# 已弃用的脚本

本目录包含在结构优化过程中被替换的重复脚本文件。

## 📁 脚本迁移记录

### Python脚本
- `cleanup_logs.py` - 日志清理脚本（已集成到 `local_dev_manager.py`）
- `cleanup_temp_files.py` - 临时文件清理脚本（已集成到 `local_dev_manager.py`）
- `start_test_services.py` - 测试服务启动脚本（已集成到 `local_dev_manager.py`）
- `run_test_with_services.py` - 带服务的测试运行脚本（已集成到 `local_dev_manager.py`）
- `monitor_system.py` - 系统监控脚本（功能已整合到新的监控工具中）

### Windows批处理脚本
- `cleanup_logs.bat` - Windows日志清理批处理（已替换为 `local_dev.bat`）
- `start_services_background.bat` - Windows后台服务启动（已替换为 `local_dev.bat`）
- `run_test.bat` - Windows测试运行批处理（已替换为 `local_dev.bat`）
- `stop_services.bat` - Windows服务停止批处理（已替换为 `local_dev.bat`）

## 🔄 替代方案

### 统一管理器
所有功能现在都集成在 `../local_dev_manager.py` 中：

```bash
# 查看状态
python scripts/local_dev_manager.py status

# 启动服务
python scripts/local_dev_manager.py start

# 停止服务
python scripts/local_dev_manager.py stop

# 运行测试
python scripts/local_dev_manager.py test

# 清理系统
python scripts/local_dev_manager.py cleanup
```

### Windows用户
使用 `../windows/local_dev.bat` 获得图形化菜单界面。

## 📝 迁移原因

1. **功能重复** - 多个脚本实现相似功能
2. **维护困难** - 分散的脚本难以统一维护
3. **用户体验** - 需要记住多个脚本命令
4. **配置不一致** - 不同脚本使用不同的配置方式

## ⚠️ 重要说明

- 这些脚本已被新工具完全替代
- 保留仅用于参考和回滚需要
- 建议在确认新工具稳定后删除此目录
- 如需回滚，可以从这里恢复原始脚本

## 🗓️ 迁移日期
2025-12-04 - 结构优化第一阶段
