import * as vscode from 'vscode';
import { execFile } from 'child_process';
import * as path from 'path';

export function activate(context: vscode.ExtensionContext) {
    console.log('🚀 LedgerMind Hardcore Zero-Touch Bridge Active');

    const getProjectPath = () => vscode.workspace.workspaceFolders?.[0].uri.fsPath || '.';

    // Create Status Bar Item
    const statusBarItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusBarItem.name = 'LedgerMind Status'; // Static identifier for context menu
    statusBarItem.text = '$(database) LedgerMind';
    statusBarItem.tooltip = 'LedgerMind Zero-Touch Bridge Active';
    statusBarItem.accessibilityInformation = { label: 'LedgerMind Zero-Touch Bridge Active', role: 'button' };
    statusBarItem.show();
    context.subscriptions.push(statusBarItem);

    // Create Output Channel for silent logging
    const outputChannel = vscode.window.createOutputChannel('LedgerMind');
    context.subscriptions.push(outputChannel);

    let isBusy = false;


    const setBusy = (busy: boolean) => {
        if (isBusy === busy) return;
        isBusy = busy;
        if (busy) {
            statusBarItem.text = '$(sync~spin) LedgerMind';
            statusBarItem.tooltip = 'LedgerMind: Syncing Context...';
            statusBarItem.accessibilityInformation = { label: 'LedgerMind Syncing Context', role: 'button' };
        } else {
            statusBarItem.text = '$(database) LedgerMind';
            statusBarItem.tooltip = 'LedgerMind Zero-Touch Bridge Active';
            statusBarItem.accessibilityInformation = { label: 'LedgerMind Zero-Touch Bridge Active', role: 'button' };
        }
    };

    // 1. HARDCORE RECORDING: Слушаем ВСЕ чат-взаимодействия (VS Code Native Chat)
    // Работает для Copilot и других встроенных чатов
    if ('chat' in (vscode as any)) {
        const chat = (vscode as any).chat;
        context.subscriptions.push(
            chat.onDidReceiveChatResponse((e: any) => {
                const projectPath = getProjectPath();
                const prompt = e.request.prompt;
                const response = e.response.map((r: any) => r.value || '').join('\n');
                
                setBusy(true);
                execFile('ledgermind-mcp', [
                    'bridge-record',
                    '--path', projectPath,
                    '--prompt', prompt,
                    '--response', response,
                    '--success',
                    '--cli', 'vscode-chat'
                ], (err) => {
                    setBusy(false);
                    if (err) outputChannel.appendLine(`LedgerMind Chat Record Error: ${err.message}`);
                });
            })
        );
    }

    // 2. TERMINAL WATCHER: Записываем всё, что происходит в терминале
    let terminalBuffer = '';
    let debounceTimer: NodeJS.Timeout | null = null;

    if ('onDidWriteTerminalData' in (vscode.window as any)) {
        context.subscriptions.push(
            (vscode.window as any).onDidWriteTerminalData((e: any) => {
                terminalBuffer += e.data;
                if (debounceTimer) clearTimeout(debounceTimer);
                
                debounceTimer = setTimeout(() => {
                    const projectPath = getProjectPath();
                    // Очистка данных от ANSI-кодов
                    const cleanData = terminalBuffer.replace(/\x1B\[[0-9;]*[JKmsu]/g, '');

                    // Фильтруем только значимые командные строки (содержат $ или >)
                    const lines = cleanData.split(/[\r\n]+/).filter((l: string) => l.trim());
                    const cmds = lines.filter((l: string) => /\$|>/.test(l)).join('; ');

                    if (cmds) {
                        execFile('ledgermind-mcp', [
                            'bridge-record',
                            '--path', projectPath,
                            '--prompt', 'Terminal Commands',
                            '--response', cmds,
                            '--success',
                            '--cli', 'vscode-terminal'
                        ], (err) => {
                            if (err) outputChannel.appendLine(`LedgerMind Terminal Record Error: ${err.message}`);
                        });
                    }
                    terminalBuffer = '';
                }, 1500); // Debounce 1.5s
            })
        );
    }

    // 3. AUTO-CONTEXT INJECTION (Shadow File Approach)
    // Мы создаем скрытый файл, который обновляется при каждом изменении фокуса или промпта.
    // Агенты (Cline/Roo) будут настроены читать этот файл автоматически.
    const updateShadowContext = async (prompt?: string) => {
        const projectPath = getProjectPath();
        const shadowFilePath = path.join(projectPath, 'ledgermind_context.md');
        
        const query = prompt || "Current project state and relevant decisions";
        
        setBusy(true);
        execFile('ledgermind-mcp', [
            'bridge-context',
            '--path', projectPath,
            '--prompt', query
        ], (err, stdout) => {
            setBusy(false);
            if (err) {
                outputChannel.appendLine(`LedgerMind Context Sync Error: ${err.message}`);
            } else if (stdout) {
                const content = `<!-- LEDGERMIND AUTONOMOUS CONTEXT - DO NOT EDIT -->\n${stdout}`;
                vscode.workspace.fs.writeFile(
                    vscode.Uri.file(shadowFilePath), 
                    Buffer.from(content)
                );
            }
        });
    };

    // Обновляем контекст при сохранении или смене активного редактора
    context.subscriptions.push(
        vscode.workspace.onDidSaveTextDocument(doc => {
            updateShadowContext(`Changes in ${path.basename(doc.fileName)}`);
            // Также записываем сохранение как эпизод
            const projectPath = getProjectPath();
            execFile('ledgermind-mcp', [
                'bridge-record',
                '--path', projectPath,
                '--prompt', 'Edit file',
                '--response', `Updated ${doc.fileName}`,
                '--success'
            ], (err) => {
                if (err) outputChannel.appendLine(`LedgerMind File Record Error: ${err.message}`);
            });
        }),
        vscode.window.onDidChangeActiveTextEditor(() => updateShadowContext())
    );

    // Начальная инициализация
    updateShadowContext();
}

export function deactivate() {}
