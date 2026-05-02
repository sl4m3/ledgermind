import * as vscode from 'vscode';
import { execFile } from 'child_process';
import * as path from 'path';
import * as fs from 'fs';

export function activate(context: vscode.ExtensionContext) {
    console.log('🚀 LedgerMind VS Code Chat Hooks Active (Dual-Hook Mode)');

    const getProjectPath = () => vscode.workspace.workspaceFolders?.[0].uri.fsPath || '.';

    // Create Status Bar Item
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.name = 'LedgerMind Status';
    statusBarItem.text = '$(database) LedgerMind';
    statusBarItem.tooltip = 'LedgerMind Dual-Hook Bridge Active (Click to view logs)';
    statusBarItem.accessibilityInformation = { label: 'LedgerMind Dual-Hook Bridge Active, click to view logs', role: 'button' };
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Create Output Channel for silent logging
    const outputChannel = vscode.window.createOutputChannel('LedgerMind');
    context.subscriptions.push(outputChannel);

    const showOutputCommandId = 'ledgermind.showOutput';
    statusBarItem.command = showOutputCommandId;

    let busyCount = 0;
    let isError = false;

    const updateStatusBar = () => {
        if (isError) {
            statusBarItem.text = busyCount > 0 ? '$(sync~spin) $(error) LedgerMind' : '$(error) LedgerMind';
            statusBarItem.tooltip = busyCount > 0 ? 'LedgerMind: Sync Error (Syncing...) (Click to view logs)' : 'LedgerMind: Sync Error (Click to view logs)';
            statusBarItem.accessibilityInformation = { label: busyCount > 0 ? 'LedgerMind Sync Error and Syncing Context, click to view logs' : 'LedgerMind Sync Error, click to view logs', role: 'button' };
            statusBarItem.backgroundColor = new vscode.ThemeColor('statusBarItem.errorBackground');
        } else if (busyCount > 0) {
            statusBarItem.backgroundColor = undefined;
            statusBarItem.text = '$(sync~spin) LedgerMind';
            statusBarItem.tooltip = 'LedgerMind: Syncing Context... (Click to view logs)';
            statusBarItem.accessibilityInformation = { label: 'LedgerMind Syncing Context, click to view logs', role: 'button' };
        } else {
            statusBarItem.backgroundColor = undefined;
            statusBarItem.text = '$(database) LedgerMind';
            statusBarItem.tooltip = 'LedgerMind Dual-Hook Bridge Active (Click to view logs)';
            statusBarItem.accessibilityInformation = { label: 'LedgerMind Dual-Hook Bridge Active, click to view logs', role: 'button' };
        }
    };

    const setError = (hasError: boolean) => {
        isError = hasError;
        updateStatusBar();
    };

    let hasShownEnoentToast = false;

    const handleExecError = (err: Error & { code?: string }, contextMsg: string) => {
        outputChannel.appendLine(`${contextMsg}: ${err.message}`);
        setError(true);
        if (err.code === 'ENOENT' && !hasShownEnoentToast) {
            hasShownEnoentToast = true;
            vscode.window.showErrorMessage(
                "LedgerMind: 'ledgermind-mcp' CLI not found. Please install it using 'pip install ledgermind' and ensure it is in your PATH."
            );
        }
    };

    const setBusy = (busy: boolean) => {
        if (busy) {
            busyCount++;
        } else {
            if (busyCount > 0) {
                busyCount--;
            }
        }
        updateStatusBar();
    };

    context.subscriptions.push(vscode.commands.registerCommand(showOutputCommandId, () => {
        outputChannel.show();
        if (isError) {
            outputChannel.appendLine('✓ Error state cleared by user');
        }
        setError(false); // Clear error state when logs are opened
    }));

    // ==========================================
    // DUAL-HOOK MECHANISM (Cache + onDidReceiveChatResponse)
    // ==========================================
    // VS Code Chat API не предоставляет событие ДО отправки промпта.
    // Решение: при onDidReceiveChatResponse:
    // 1) bridge-record (предыдущий запрос из кэша)
    // 2) bridge-context (текущий промпт → shadow file)

    interface CachedInteraction {
        prompt: string;
        response: string;
        timestamp: number;
    }

    let previousInteraction: CachedInteraction | null = null;

    const recordPreviousInteraction = async (interaction: CachedInteraction) => {
        if (!interaction || !interaction.prompt || !interaction.response) {
            return;
        }

        const projectPath = getProjectPath();
        setBusy(true);

        return new Promise<void>((resolve) => {
            execFile('ledgermind-mcp', [
                'bridge-record',
                '--path', projectPath,
                '--prompt', interaction.prompt,
                '--response', interaction.response,
                '--success',
                '--cli', 'vscode-chat'
            ], (err) => {
                setBusy(false);
                if (err) {
                    handleExecError(err as Error & { code?: string }, 'LedgerMind Record Error');
                } else {
                    outputChannel.appendLine(`✓ Recorded previous interaction: "${interaction.prompt.substring(0, 50)}..."`);
                }
                resolve();
            });
        });
    };

    const updateShadowContext = async (prompt: string) => {
        const projectPath = getProjectPath();
        const shadowFilePath = path.join(projectPath, 'ledgermind_context.md');

        setBusy(true);

        return new Promise<void>((resolve) => {
            execFile('ledgermind-mcp', [
                'bridge-context',
                '--path', projectPath,
                '--prompt', prompt,
                '--cli', 'vscode-chat'
            ], (err, stdout) => {
                setBusy(false);
                if (err) {
                    handleExecError(err as Error & { code?: string }, 'LedgerMind Context Sync Error');
                } else if (stdout) {
                    const content = `<!-- LEDGERMIND AUTONOMOUS CONTEXT - DO NOT EDIT -->
<!-- Updated: ${new Date().toISOString()} -->
<!-- Prompt: ${prompt.substring(0, 100)}... -->

${stdout}`;

                    try {
                        fs.writeFileSync(shadowFilePath, content, 'utf-8');
                        outputChannel.appendLine(`✓ Updated shadow context: ${path.basename(shadowFilePath)}`);
                    } catch (writeErr) {
                        outputChannel.appendLine(`LedgerMind Shadow File Error: ${(writeErr as Error).message}`);
                        setError(true);
                    }
                }
                resolve();
            });
        });
    };

    // ==========================================
    // 1. VS CODE NATIVE CHAT (Copilot Chat, Qwen Code extension)
    // ==========================================
    if ('chat' in (vscode as any)) {
        const chat = (vscode as any).chat;

        // FIX: Register chat variable resolver to prevent InvalidStateError crash
        if (chat.registerChatVariableResolver) {
            context.subscriptions.push(
                chat.registerChatVariableResolver('ledgermind', 'Inject relevant context from LedgerMind autonomous memory', {
                    resolve(name: string, context: any, token: vscode.CancellationToken) {
                        const projectPath = getProjectPath();
                        const shadowFilePath = path.join(projectPath, 'ledgermind_context.md');
                        let contextContent = '';
                        if (fs.existsSync(shadowFilePath)) {
                            contextContent = fs.readFileSync(shadowFilePath, 'utf-8');
                        }
                        
                        return [
                            {
                                level: (vscode as any).ChatVariableLevel?.Full || 1,
                                value: contextContent || 'No context available.'
                            }
                        ];
                    }
                })
            );
        }

        if (chat.onDidReceiveChatResponse) {
            context.subscriptions.push(
                chat.onDidReceiveChatResponse(async (e: any) => {
                    const prompt = e.request?.prompt || '';
                    const response = e.response?.map((r: any) => r.value || '').join('\n') || '';

                    if (!prompt || !response) {
                        return;
                    }

                    outputChannel.appendLine(`\n--- VS Code Chat Response ---`);
                    outputChannel.appendLine(`Prompt: "${prompt.substring(0, 80)}..."`);

                    // Хук 1: Записать ПРЕДЫДУЩЕЕ взаимодействие (из кэша)
                    if (previousInteraction) {
                        outputChannel.appendLine(`→ Recording previous interaction...`);
                        await recordPreviousInteraction(previousInteraction);
                    }

                    // Хук 2: Получить контекст для ТЕКУЩЕГО промпта → shadow file
                    outputChannel.appendLine(`→ Updating shadow context...`);
                    await updateShadowContext(prompt);

                    // Кэшировать ТЕКУЩЕЕ взаимодействие для следующего вызова
                    previousInteraction = {
                        prompt,
                        response,
                        timestamp: Date.now()
                    };
                })
            );
        }
    }

    // ==========================================
    // 2. FILE WATCHER для Roo Code/Cline history
    // ==========================================
    // Следим за файлами истории Roo Code/Cline
    const historyWatchPaths = [
        '.roo/history.json',
        '.roo/code.json',
        '.cline/history.json',
        '.cline/messages.json',
    ];

    const fileWatchers: vscode.FileSystemWatcher[] = [];

    for (const watchPath of historyWatchPaths) {
        const projectPath = getProjectPath();
        const fullPath = path.join(projectPath, watchPath);

        // Проверяем, существует ли файл
        if (!fs.existsSync(fullPath)) {
            continue;
        }

        const pattern = new vscode.RelativePattern(projectPath, watchPath);
        const watcher = vscode.workspace.createFileSystemWatcher(pattern, false, false, false);

        // Debounce для избежания множественных вызовов
        let debounceTimer: NodeJS.Timeout | null = null;

        watcher.onDidChange(async (uri) => {
            if (debounceTimer) clearTimeout(debounceTimer);

            debounceTimer = setTimeout(async () => {
                try {
                    const content = fs.readFileSync(uri.fsPath, 'utf-8');
                    const history = JSON.parse(content);

                    // Получаем последние взаимодействия
                    const turns = history.turns || history.messages || [];
                    if (turns.length < 2) {
                        return;
                    }

                    // Берём последние user + assistant turns
                    const lastTurns = turns.slice(-2);
                    const userTurn = lastTurns.find((t: any) => t.role === 'user' || t.type === 'user');
                    const assistantTurn = lastTurns.find((t: any) => t.role === 'assistant' || t.role === 'agent');

                    if (userTurn && assistantTurn) {
                        const prompt = userTurn.content || userTurn.text || '';
                        const response = assistantTurn.content || assistantTurn.text || '';

                        if (prompt && response) {
                            // Записать в LedgerMind
                            setBusy(true);
                            execFile('ledgermind-mcp', [
                                'bridge-record',
                                '--path', projectPath,
                                '--prompt', prompt,
                                '--response', response,
                                '--success',
                                '--cli', 'vscode-roocode'
                            ], (err) => {
                                setBusy(false);
                                if (err) {
                                    handleExecError(err as Error & { code?: string }, 'LedgerMind RooCode Record Error');
                                } else {
                                    outputChannel.appendLine(`✓ Recorded RooCode/Cline interaction via file watcher`);
                                }
                            });

                            // Обновить shadow context
                            await updateShadowContext(prompt);
                        }
                    }
                } catch (err) {
                    outputChannel.appendLine(`LedgerMind File Watcher Error: ${(err as Error).message}`);
                    setError(true);
                }
            }, 2000); // Debounce 2s
        });

        fileWatchers.push(watcher);
        context.subscriptions.push(watcher);
    }

    // ==========================================
    // 3. TERMINAL WATCHER (дополнительно)
    // ==========================================
    let terminalBuffer = '';
    let terminalDebounceTimer: NodeJS.Timeout | null = null;

    if ('onDidWriteTerminalData' in (vscode.window as any)) {
        context.subscriptions.push(
            (vscode.window as any).onDidWriteTerminalData((e: any) => {
                terminalBuffer += e.data;
                if (terminalDebounceTimer) clearTimeout(terminalDebounceTimer);

                terminalDebounceTimer = setTimeout(() => {
                    const projectPath = getProjectPath();
                    const cleanData = terminalBuffer.replace(/\x1B\[[0-9;]*[JKmsu]/g, '');

                    const lines = cleanData.split(/[\r\n]+/).filter((l: string) => l.trim());
                    const cmds = lines.filter((l: string) => /\$|>/.test(l)).join('; ');

                    if (cmds) {
                        setBusy(true);
                        execFile('ledgermind-mcp', [
                            'bridge-record',
                            '--path', projectPath,
                            '--prompt', 'Terminal Commands',
                            '--response', cmds,
                            '--success',
                            '--cli', 'vscode-terminal'
                        ], (err) => {
                            setBusy(false);
                            if (err) {
                                handleExecError(err as Error & { code?: string }, 'LedgerMind Terminal Record Error');
                            }
                        });
                    }
                    terminalBuffer = '';
                }, 1500);
            })
        );
    }

    // ==========================================
    // 4. FILE SAVE WATCHER (дополнительно)
    // ==========================================
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(doc => {
            const projectPath = getProjectPath();
            const fileName = path.basename(doc.fileName);

            // Обновляем shadow context при сохранении
            updateShadowContext(`Changes in ${fileName}`);

            // Записываем сохранение как эпизод
            setBusy(true);
            execFile('ledgermind-mcp', [
                'bridge-record',
                '--path', projectPath,
                '--prompt', 'Edit file',
                '--response', `Updated ${fileName}`,
                '--success',
                '--cli', 'vscode-editor'
            ], (err) => {
                setBusy(false);
                if (err) {
                    handleExecError(err as Error & { code?: string }, 'LedgerMind File Record Error');
                }
            });
        })
    );

    // Начальная инициализация - создаём shadow file
    const initialShadowPath = path.join(getProjectPath(), 'ledgermind_context.md');
    if (!fs.existsSync(initialShadowPath)) {
        const initialContent = `<!-- LEDGERMIND AUTONOMOUS CONTEXT - DO NOT EDIT -->
<!-- Created: ${new Date().toISOString()} -->
<!-- AI agents should read this file at the start of every task -->

# LedgerMind Context

This file contains relevant context for the current task.
It is updated automatically based on your previous interactions.

---

*No context available yet. Start by exploring the project structure.*
`;
        fs.writeFileSync(initialShadowPath, initialContent, 'utf-8');
    }

    outputChannel.appendLine('✓ LedgerMind VS Code Chat Hooks initialized');
}

export function deactivate() {
    console.log('LedgerMind VS Code Chat Hooks deactivated');
}
