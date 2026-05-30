/**
 * 简单 i18n — 支持中英文切换
 */

type Lang = 'zh' | 'en';

const translations: Record<string, Record<Lang, string>> = {
  // 侧边栏
  'sidebar.newChat': { zh: '新建对话', en: 'New Chat' },
  'sidebar.settings': { zh: '设置', en: 'Settings' },
  'sidebar.sessions': { zh: '对话列表', en: 'Sessions' },
  'sidebar.delete': { zh: '删除', en: 'Delete' },
  'sidebar.rename': { zh: '重命名', en: 'Rename' },

  // 聊天
  'chat.input.placeholder': { zh: '输入消息... (Shift+Enter 换行)', en: 'Type a message... (Shift+Enter for new line)' },
  'chat.send': { zh: '发送', en: 'Send' },
  'chat.stop': { zh: '停止', en: 'Stop' },
  'chat.thinking': { zh: '正在思考...', en: 'Thinking...' },
  'chat.thinkingProcess': { zh: '思考过程', en: 'Thinking Process' },
  'chat.quickActions': { zh: '快捷操作', en: 'Quick Actions' },
  'chat.quick1': { zh: '帮我写一段 Python 代码', en: 'Write Python code for me' },
  'chat.quick2': { zh: '解释一下这个概念', en: 'Explain this concept' },
  'chat.quick3': { zh: '帮我分析数据', en: 'Help me analyze data' },
  'chat.quick4': { zh: '翻译这段文字', en: 'Translate this text' },
  'chat.attaching': { zh: '上传中...', en: 'Uploading...' },
  'chat.backendOffline': { zh: '后端离线', en: 'Backend Offline' },
  'chat.stopped': { zh: '已停止生成', en: 'Generation stopped' },

  // 工具
  'tool.pending': { zh: '等待中', en: 'Pending' },
  'tool.running': { zh: '执行中', en: 'Running' },
  'tool.completed': { zh: '已完成', en: 'Completed' },
  'tool.error': { zh: '出错', en: 'Error' },
  'tool.read_file': { zh: '读取文件', en: 'Read File' },
  'tool.write_file': { zh: '写入文件', en: 'Write File' },
  'tool.list_files': { zh: '列出文件', en: 'List Files' },
  'tool.search_files': { zh: '搜索文件', en: 'Search Files' },
  'tool.terminal': { zh: '执行命令', en: 'Run Command' },
  'tool.web_search': { zh: '网页搜索', en: 'Web Search' },
  'tool.web_extract': { zh: '提取网页', en: 'Extract Web' },
  'tool.create_word': { zh: '创建Word', en: 'Create Word' },
  'tool.create_ppt': { zh: '创建PPT', en: 'Create PPT' },
  'tool.create_excel': { zh: '创建Excel', en: 'Create Excel' },
  'tool.read_word': { zh: '读取Word', en: 'Read Word' },
  'tool.read_excel': { zh: '读取Excel', en: 'Read Excel' },
  'tool.edit_word': { zh: '编辑Word', en: 'Edit Word' },
  'tool.edit_excel': { zh: '编辑Excel', en: 'Edit Excel' },

  // 设置
  'settings.title': { zh: '设置', en: 'Settings' },
  'settings.general': { zh: '通用', en: 'General' },
  'settings.model': { zh: '模型', en: 'Model' },
  'settings.skills': { zh: '技能', en: 'Skills' },
  'settings.network': { zh: '网络', en: 'Network' },
  'settings.email': { zh: '邮件', en: 'Email' },
  'settings.about': { zh: '关于', en: 'About' },
  'settings.language': { zh: '语言', en: 'Language' },
  'settings.fontSize': { zh: '字体大小', en: 'Font Size' },
  'settings.temperature': { zh: '温度', en: 'Temperature' },
  'settings.maxTokens': { zh: '最大 Token 数', en: 'Max Tokens' },
  'settings.sendShortcut': { zh: '发送快捷键', en: 'Send Shortcut' },
  'settings.systemPrompt': { zh: '系统提示词', en: 'System Prompt' },
  'settings.backendUrl': { zh: '后端地址', en: 'Backend URL' },

  // 邮件
  'email.inbox': { zh: '收件箱', en: 'Inbox' },
  'email.compose': { zh: '写邮件', en: 'Compose' },
  'email.from': { zh: '发件人', en: 'From' },
  'email.to': { zh: '收件人', en: 'To' },
  'email.subject': { zh: '主题', en: 'Subject' },
  'email.date': { zh: '日期', en: 'Date' },
  'email.attachments': { zh: '附件', en: 'Attachments' },
  'email.noEmails': { zh: '暂无邮件', en: 'No emails' },
  'email.refresh': { zh: '刷新', en: 'Refresh' },

  // 通用
  'common.save': { zh: '保存', en: 'Save' },
  'common.cancel': { zh: '取消', en: 'Cancel' },
  'common.confirm': { zh: '确认', en: 'Confirm' },
  'common.delete': { zh: '删除', en: 'Delete' },
  'common.close': { zh: '关闭', en: 'Close' },
  'common.loading': { zh: '加载中...', en: 'Loading...' },
  'common.error': { zh: '错误', en: 'Error' },
  'common.success': { zh: '成功', en: 'Success' },
  'common.search': { zh: '搜索', en: 'Search' },
  'common.copy': { zh: '复制', en: 'Copy' },
  'common.copied': { zh: '已复制', en: 'Copied' },
};

let currentLang: Lang = 'zh';

export function setLang(lang: Lang) {
  currentLang = lang;
}

export function getLang(): Lang {
  return currentLang;
}

export function t(key: string): string {
  const entry = translations[key];
  if (!entry) return key;
  return entry[currentLang] || entry.zh || key;
}
