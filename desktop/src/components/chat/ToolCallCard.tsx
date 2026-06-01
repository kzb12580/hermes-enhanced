import React, { useState } from 'react';
import { ChevronDown, ChevronRight, Wrench, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { ParsedToolCall } from '../../stores/chatStore';

interface ToolCallCardProps {
  toolCall: ParsedToolCall;
}

export function ToolCallCard({ toolCall }: ToolCallCardProps) {
  // 执行中时自动展开，完成后自动收起
  const [expanded, setExpanded] = useState(toolCall.status === 'running');

  // 状态变化时自动展开/收起
  React.useEffect(() => {
    if (toolCall.status === 'running') {
      setExpanded(true);
    }
  }, [toolCall.status]);

  const statusIcon = {
    pending: <Loader2 size={14} className="animate-spin text-text-muted" />,
    running: <Loader2 size={14} className="animate-spin text-accent" />,
    completed: <CheckCircle size={14} className="text-success" />,
    error: <XCircle size={14} className="text-error" />,
  };

  const statusText = {
    pending: '等待中',
    running: '执行中',
    completed: '已完成',
    error: '出错',
  };

  // 工具中文名称映射
  const toolNameCN: Record<string, string> = {
    read_file: '读取文件',
    write_file: '写入文件',
    list_files: '列出文件',
    search_files: '搜索文件',
    terminal: '执行命令',
    web_search: '网页搜索',
    web_extract: '提取网页',
    screen_capture: '屏幕截图',
    ocr_extract: 'OCR识别',
    create_word: '创建Word',
    edit_word: '编辑Word',
    read_word: '读取Word',
    create_ppt: '创建PPT',
    create_excel: '创建Excel',
    read_excel: '读取Excel',
    edit_excel: '编辑Excel',
    mouse_click: '🖱️ 点击',
    mouse_move: '🖱️ 移动',
    mouse_drag: '🖱️ 拖拽',
    mouse_scroll: '🖱️ 滚动',
    keyboard_type: '⌨️ 输入',
    keyboard_hotkey: '⌨️ 快捷键',
    keyboard_press: '⌨️ 按键',
    list_windows: '🪟 列出窗口',
    find_window: '🪟 查找窗口',
    bring_to_front: '🪟 置前窗口',
    wait: '⏳ 等待',
    get_mouse_position: '🖱️ 获取位置',
    get_screen_size: '📐 屏幕尺寸',
    // Memory tools
    save_memory: '💾 保存记忆',
    search_memory: '🔍 搜索记忆',
    list_memories: '📋 列出记忆',
    delete_memory: '🗑️ 删除记忆',
    // Session tools
    search_session: '🔍 搜索会话',
    get_session_history: '📜 会话历史',
    // Todo tools
    todo_create: '📝 创建待办',
    todo_update: '✏️ 更新待办',
    todo_list: '📋 待办列表',
    // Verify tools
    verify_file: '✅ 验证文件',
    verify_command: '✅ 验证命令',
    // Code execution
    execute_code: '💻 执行代码',
    // Skill tools
    save_skill: '⚡ 保存技能',
    list_skills: '⚡ 技能列表',
    load_skill: '⚡ 加载技能',
    delete_skill: '⚡ 删除技能',
  };

  const displayName = toolNameCN[toolCall.name] || toolCall.name;

  let parsedArgs: string;
  try {
    parsedArgs = JSON.stringify(JSON.parse(toolCall.arguments), null, 2);
  } catch {
    parsedArgs = toolCall.arguments || '{}';
  }

  let parsedResult: string = '';
  try {
    if (toolCall.result) {
      parsedResult = JSON.stringify(JSON.parse(toolCall.result), null, 2);
    }
  } catch {
    parsedResult = toolCall.result || '';
  }

  return (
    <div className="my-2 rounded-lg border border-border bg-bg-secondary overflow-hidden fade-in">
      {/* Header */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left hover:bg-bg-tertiary transition-colors"
      >
        {expanded ? (
          <ChevronDown size={14} className="text-text-muted flex-shrink-0" />
        ) : (
          <ChevronRight size={14} className="text-text-muted flex-shrink-0" />
        )}
        <Wrench size={14} className="text-accent flex-shrink-0" />
        <span className="text-sm font-medium text-text-primary truncate">
          {displayName}
        </span>
        {toolCall.status === 'running' && (
          <span className="text-xs text-accent animate-pulse">
            正在{displayName}...
          </span>
        )}
        <span className="ml-auto flex items-center gap-1.5 text-xs text-text-muted">
          {statusIcon[toolCall.status]}
          <span>{statusText[toolCall.status]}</span>
        </span>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-border p-3 space-y-3">
          {/* Arguments */}
          <div>
            <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1">
              参数
            </h4>
            <pre className="text-xs font-mono bg-bg-primary rounded p-2 overflow-x-auto text-text-secondary max-h-48 overflow-y-auto">
              {parsedArgs}
            </pre>
          </div>

          {/* Result */}
          {toolCall.result && (
            <div>
              <h4 className="text-xs font-semibold text-text-muted uppercase tracking-wider mb-1">
                结果
              </h4>
              <pre className="text-xs font-mono bg-bg-primary rounded p-2 overflow-x-auto text-text-secondary max-h-64 overflow-y-auto">
                {parsedResult}
              </pre>
            </div>
          )}

          {toolCall.status === 'running' && !toolCall.result && (
            <div className="flex items-center gap-2 text-xs text-text-muted">
              <Loader2 size={12} className="animate-spin" />
              <span>正在执行工具...</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default ToolCallCard;
