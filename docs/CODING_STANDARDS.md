# Athena Trader 项目编码规范

## 文件编码规范

### UTF-8 编码要求

1. **禁止使用 UTF-8 BOM**
   - 所有 Python 文件必须使用无 BOM 的 UTF-8 编码
   - UTF-8 BOM（字节顺序标记 `\xef\xbb\xbf`）可能导致 Python 解析错误
   - 特别是在使用 shebang (`#!/usr/bin/env python`) 的文件中

2. **检查和修复工具**
   - 使用项目提供的 `scripts/fix_bom.py` 脚本检查和修复 BOM 问题
   - Git pre-commit hook 会自动检查暂存的 Python 文件

### 检查命令

```bash
# 扫描所有 Python 文件的 BOM 状态
python scripts/fix_bom.py --dry-run

# 修复发现的 BOM 问题
python scripts/fix_bom.py

# 不创建备份的修复（谨慎使用）
python scripts/fix_bom.py --no-backup
```

## 编辑器配置

### VS Code 配置

在项目根目录的 `.vscode/settings.json` 中添加：

```json
{
    "files.encoding": "utf8",
    "files.autoGuessEncoding": false,
    "files.insertFinalNewline": true,
    "files.trimTrailingWhitespace": true,
    "[python]": {
        "files.encoding": "utf8",
        "files.insertFinalNewline": true,
        "files.trimTrailingWhitespace": true
    }
}
```

### 其他编辑器

- **PyCharm**: File → Settings → Editor → File Encodings → 设置 IDE Encoding 和 Project Encoding 为 UTF-8
- **Sublime Text**: Preferences → Settings → 确保 `"default_encoding": "UTF-8"`
- **Vim/Neovim**: 在 `.vimrc` 中添加 `set encoding=utf-8 fileencoding=utf-8`
- **Emacs**: 在 `.emacs` 中添加 `(set-default-coding-systems 'utf-8)`

## Git 配置

### Pre-commit Hook

项目已配置 Git pre-commit hook 来防止引入 BOM：

- 自动检查暂存的 Python 文件
- 如果发现 BOM，会阻止提交并提示修复方法
- 提供清晰的错误信息和修复建议

### Git 全局配置

```bash
# 设置 Git 处理文本文件的编码
git config --global core.quotepath false
git config --global i18n.commitencoding utf-8
git config --global i18n.logoutputencoding utf-8
```

## 常见问题

### Q: 为什么不能使用 UTF-8 BOM？

A: UTF-8 BOM 可能导致以下问题：
1. Python 解释器无法正确解析文件开头的 shebang
2. 某些工具和库可能无法正确处理带 BOM 的文件
3. BOM 字符可能被包含在字符串字面量中
4. 在某些系统上可能导致编码混乱

### Q: 如何检查文件是否包含 BOM？

A: 使用以下方法：
1. 运行 `python scripts/fix_bom.py --dry-run`
2. 使用十六进制编辑器查看文件开头是否有 `\xef\xbb\xbf`
3. 使用 `file` 命令（Linux/Mac）检查文件编码

### Q: 如果不小心提交了带 BOM 的文件怎么办？

A: 按以下步骤修复：
1. 运行 `python scripts/fix_bom.py` 修复 BOM
2. 提交修复后的文件
3. 如果需要，使用 `git rebase` 修复历史提交

### Q: 备份文件在哪里？

A: BOM 修复脚本会在 `.bom_backups/` 目录中创建备份，保持与原文件相同的目录结构。

## 最佳实践

1. **编辑器配置**: 确保编辑器默认使用无 BOM 的 UTF-8 编码
2. **定期检查**: 在重要提交前运行 BOM 检查
3. **团队协作**: 确保所有团队成员了解编码规范
4. **CI/CD 集成**: 在持续集成流程中添加 BOM 检查

## 相关工具

- `scripts/fix_bom.py`: 项目 BOM 检查和修复工具
- `.git/hooks/pre-commit`: Git pre-commit hook
- `.vscode/settings.json`: VS Code 配置（推荐）

## 更新日志

- 2025-12-05: 初始版本，建立 UTF-8 无 BOM 编码规范
- 添加自动化检查和修复工具
- 配置 Git pre-commit hook
