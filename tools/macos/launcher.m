// Native LaunchServices entry point; configuration is supplied by create_app.py.
#import <AppKit/AppKit.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static int failed(NSString *message) {
    fprintf(stderr, "Ankang startup failed: %s\n", message.UTF8String);
    fflush(stderr);
    NSAlert *alert = [[NSAlert alloc] init];
    alert.messageText = @"安康启动失败";
    alert.informativeText = message;
    [alert addButtonWithTitle:@"好"];
    [alert runModal];
    return 1;
}

int main(int argc, char **argv) {
    @autoreleasepool {
        NSString *root = @(ANKANG_ROOT);
        NSString *runtime = [root stringByAppendingPathComponent:@".runtime"];
        NSError *error = nil;
        if (![[NSFileManager defaultManager] createDirectoryAtPath:runtime
                withIntermediateDirectories:YES attributes:nil error:&error]) {
            return failed([NSString stringWithFormat:@"无法访问项目目录：%@\n%@", root, error.localizedDescription]);
        }
        NSString *log = [runtime stringByAppendingPathComponent:@"portrait.log"];
        if (!freopen(log.fileSystemRepresentation, "a", stdout) ||
                !freopen(log.fileSystemRepresentation, "a", stderr)) {
            return failed(@"无法写入启动日志，请检查项目目录的访问权限。");
        }
        fprintf(stderr, "\n[%s] Ankang native launcher revision 2\n", NSDate.date.description.UTF8String);
        fflush(stderr);
        if (chdir(ANKANG_ROOT) != 0) {
            return failed([NSString stringWithFormat:@"无法打开项目目录：%s", strerror(errno)]);
        }
        setenv("ANKANG_NODE", ANKANG_NODE, 1);
        char **arguments = calloc((size_t)argc + 3, sizeof(char *));
        if (!arguments) return failed(@"内存不足，请稍后重试。");
        arguments[0] = ANKANG_PYTHON;
        arguments[1] = "-m";
        arguments[2] = "mobile_rehab.portrait";
        for (int i = 1; i < argc; ++i) arguments[i + 2] = argv[i];
        execv(ANKANG_PYTHON, arguments);
        return failed([NSString stringWithFormat:@"无法启动 Python 环境：%s\n请保留项目文件夹及其中的 .venv 环境。", strerror(errno)]);
    }
}
