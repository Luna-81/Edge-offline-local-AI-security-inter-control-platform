#include "../../server/AegisNet/src/base/Logger.h"
#include "../../include/GlobalRegistry.h"
#include "../../include/utils/AegisUtils.h"
#include <filesystem>
#include <ctime>
#include <iostream>
#include <chrono>
#include <unistd.h>
#include <sys/wait.h>
#include <mutex>
#include <regex>
#include <memory>
#include <sys/inotify.h>
#include <sys/poll.h>
#include <vector>
#include <iomanip>
#include <sstream>
#include <unordered_map>
#include <hiredis/hiredis.h>
#include <algorithm>
#include <fcntl.h>

namespace fs = std::filesystem;

// [优化] 分支预测宏
#ifndef unlikely
#define unlikely(x) __builtin_expect(!!(x), 0)
#endif

// --- 资源管理辅助结构 (RAII) ---
struct RedisReplyDeleter {
    void operator()(redisReply *r) const { if (r) freeReplyObject(r); }
};
using ReplyPtr = std::unique_ptr<redisReply, RedisReplyDeleter>;

struct RedisContextDeleter {
    void operator()(redisContext *c) const { if (c) redisFree(c); }
};
using ContextPtr = std::unique_ptr<redisContext, RedisContextDeleter>;

namespace Config {
    constexpr const char *REDIS_HOST = "127.0.0.1";
    constexpr int REDIS_PORT = 6379;
    constexpr const char *GOLDEN_CONF = "/app/recovery_vault/core.conf.bak";
    constexpr const char *CORE_CONF = "/app/core.conf";
    constexpr const char *NFT_BIN = "/usr/sbin/nft";
    constexpr const char *NSENTER_BIN = "/usr/bin/nsenter";
}

namespace RedisKeys {
    constexpr const char *STATE = "knowpasser:state";
    constexpr const char *CMD_QUEUE = "knowpasser:cmd_queue";
    constexpr const char *ALERTS = "knowpasser:alerts";
    constexpr const char *METRICS_NODE = "node:Hamilton-East:metrics";
}

// ==========================================================
// GlobalRegistry 实现 [Hamilton SOC Edition v10.1 - Optimized]
// ==========================================================

GlobalRegistry &GlobalRegistry::getInstance() {
    static GlobalRegistry instance;
    return instance;
}

// 统一构造函数：处理所有初始化逻辑
GlobalRegistry::GlobalRegistry() : redis_ctx_(nullptr), running_(false) {
    ready_.store(false);
    
    struct timeval timeout = {1, 500000}; 
    redis_ctx_ = redisConnectWithTimeout(Config::REDIS_HOST, Config::REDIS_PORT, timeout);
    
    if (redis_ctx_ && redis_ctx_->err) {
        LOG_ERROR << "❌ Redis connection error: " << redis_ctx_->errstr;
    } else if (redis_ctx_) {
        LOG_INFO << "✅ Registry connected to Redis.";
    }
}

GlobalRegistry::~GlobalRegistry() { 
    stop(); 
    std::lock_guard<std::mutex> lock(redis_mtx_);
    if (redis_ctx_) {
        redisFree(redis_ctx_);
        redis_ctx_ = nullptr;
    }
}

void GlobalRegistry::start() {
    bool expected = false;
    if (!running_.compare_exchange_strong(expected, true)) return;

    // 清理旧状态
    ContextPtr init_ctx(redisConnect(Config::REDIS_HOST, Config::REDIS_PORT));
    if (init_ctx && !init_ctx->err) {
        redisCommand(init_ctx.get(), "DEL %s", RedisKeys::STATE);
    }

    ready_.store(true, std::memory_order_release);

    // 1. 遥测同步线程
    background_workers_.emplace_back([this]() {
        LOG_INFO << "Registry: Telemetry Sync Heartbeat Active.";
        while (running_.load()) {
            this->syncToRemote();
            std::unique_lock<std::mutex> lock(cv_mutex_);
            if (cv_.wait_for(lock, std::chrono::seconds(1), [this]{ return !running_.load(); })) break;
        } 
    });

    // 2. 命令监听线程
    background_workers_.emplace_back([this]() { this->startCommandListener(); });

    // 3. 文件自愈线程
    background_workers_.emplace_back([this]() { this->startHotHealingWatcher(); });

    LOG_INFO << "🛡️ AegisNet v10.1 Core [Hamilton-East] - Pure Management Plane Active.";
}

void GlobalRegistry::stop() {
    bool expected = true;
    if (running_.compare_exchange_strong(expected, false)) {
        LOG_INFO << "Shutting down AegisNet Core Management Plane...";
        cv_.notify_all();
        for (auto &worker : background_workers_) {
            if (worker.joinable()) worker.join();
        }
        background_workers_.clear();
    }
}

bool GlobalRegistry::syncToRemote() {
    try {
        thread_local ContextPtr tl_context(nullptr);
        if (!tl_context || tl_context->err) {
            struct timeval timeout = {0, 800000};
            tl_context.reset(redisConnectWithTimeout(Config::REDIS_HOST, Config::REDIS_PORT, timeout));
            if (!tl_context || tl_context->err) return false;
        }

        std::unordered_map<std::string, std::string> snapshot;
        {
            std::lock_guard<std::mutex> lock(metrics_mtx_);
            snapshot = metrics_cache_;
        }
        if (snapshot.empty()) return true;

        for (auto const &[key, val] : snapshot) {
            ReplyPtr reply(static_cast<redisReply *>(
                redisCommand(tl_context.get(), "HSET %s %s %s", RedisKeys::STATE, key.c_str(), val.c_str())));
            if (!reply || tl_context->err) return false;
        }

        auto now_sec = std::chrono::system_clock::to_time_t(std::chrono::system_clock::now());
        redisCommand(tl_context.get(), "HMSET %s node Hamilton-East last_seen %ld", RedisKeys::STATE, (long)now_sec);
        redisCommand(tl_context.get(), "EXPIRE %s 60", RedisKeys::STATE);

        return true;
    } catch (...) { return false; }
}

void GlobalRegistry::dispatchMetric(const std::string& json, 
                                    double cpu, 
                                    double mem, 
                                    double disk_r, 
                                    double disk_w, 
                                    double net_in, 
                                    double net_out){
    // 1. 实时路径：写入 Redis (注意先锁后判)
    {
        std::lock_guard<std::mutex> lock(redis_mtx_);
        if (redis_ctx_ && !redis_ctx_->err) {
            ReplyPtr reply(static_cast<redisReply *>(
                redisCommand(redis_ctx_, "SET %s %s", RedisKeys::METRICS_NODE, json.c_str())));
            if (!reply || redis_ctx_->err) LOG_ERROR << "🚨 Redis set failed in dispatchMetric";
        }
    }

    // 2. 异常路径：强制写入 FIFO 供大脑分析
    if (cpu > 10.0 || mem > 10.0) {
        AegisUtils::getInstance().processAndStore(json);
    }
}

void GlobalRegistry::reportSecurityEvent(const std::string& target, const std::string& details) {
    // A. 逻辑触发：特定安全事件自愈
    if (target == "FILE_BREACH") {
        LOG_WARN << "🛡️ Configuration Compromise Detected. Triggering Recovery...";
        this->ensureConfigIntegrity();
    }

    // B. 构造标准安全 JSON
    std::stringstream ss;
    ss << "{\"type\":\"SECURITY\",\"node\":\"Hamilton-East\","
       << "\"event\":\"" << target << "\",\"data\":\"" << details << "\","
       << "\"timestamp\":" << std::time(nullptr) << "}";
    std::string sec_payload = ss.str();

    // C. 写入 FIFO (大脑 run.py 感知)
    AegisUtils::getInstance().processAndStore(sec_payload);
    
    // D. 写入 Redis 报警队列 (前端面板感知)
    {
        std::lock_guard<std::mutex> lock(redis_mtx_); 
        if (redis_ctx_) {
            ReplyPtr reply(static_cast<redisReply*>(
                redisCommand(redis_ctx_, "LPUSH %s %s", RedisKeys::ALERTS, sec_payload.c_str())
            ));
        }
    }
}

void GlobalRegistry::updateMetric(const std::string &key, const std::string &value) {
    std::lock_guard<std::mutex> lock(metrics_mtx_);
    metrics_cache_[key] = value;
}

void GlobalRegistry::updateRawData(const std::string &key, const std::string &value) {
    if (key == "HARDWARE_LOCK")
        hardware_lock_requested_.store(value == "true", std::memory_order_relaxed);
    this->updateMetric(key, value);
}

// --- 下行指令链路 ---
void GlobalRegistry::startCommandListener() {
    while (running_.load()) {
        ContextPtr sub_ctx(redisConnect(Config::REDIS_HOST, Config::REDIS_PORT));
        if (!sub_ctx || sub_ctx->err) {
            std::unique_lock<std::mutex> lock(cv_mutex_);
            cv_.wait_for(lock, std::chrono::seconds(5));
            continue;
        }
        while (running_.load()) {
            ReplyPtr reply(static_cast<redisReply *>(redisCommand(sub_ctx.get(), "BLPOP %s 2", RedisKeys::CMD_QUEUE)));
            if (!reply || sub_ctx->err) break;
            if (reply->type == REDIS_REPLY_ARRAY && reply->elements >= 2) {
                if (reply->element[1]->str) executeAction(reply->element[1]->str);
            }
        }
    }
}

void GlobalRegistry::executeAction(const std::string &cmd) {
    if (cmd.rfind("BLOCK_IP:", 0) == 0) blockIP(cmd.substr(9));
    else if (cmd.rfind("UNBLOCK_IP:", 0) == 0) unblockIP(cmd.substr(11));
}

// [优化] 抽离公共的 Shell 执行逻辑
void executeNetCommand(const std::vector<std::string>& args) {
    pid_t pid = fork();
    if (pid == 0) {
        std::vector<char *> c_args;
        c_args.push_back(const_cast<char *>(Config::NSENTER_BIN));
        for (const auto &arg : args) c_args.push_back(const_cast<char *>(arg.c_str()));
        c_args.push_back(nullptr);
        execv(Config::NSENTER_BIN, c_args.data());
        exit(1);
    }
    waitpid(pid, nullptr, 0);
}

void GlobalRegistry::blockIP(const std::string &ip) {
    static const std::regex pattern(R"(^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$)");
    if (!std::regex_match(ip, pattern)) return;

    LOG_INFO << "🛡️ Control Plane [BLOCK_IP]: " << ip;
    executeNetCommand({"-t", "1", "-n", Config::NFT_BIN, "add", "element", "inet", "knowpasser", "blackhole", "{", ip, "}"});
}

void GlobalRegistry::unblockIP(const std::string &ip) {
    static const std::regex pattern(R"(^(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(\.(25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3}$)");
    if (!std::regex_match(ip, pattern)) return;

    LOG_INFO << "🛡️ Control Plane [UNBLOCK_IP]: " << ip;
    executeNetCommand({"-t", "1", "-n", Config::NFT_BIN, "delete", "element", "inet", "knowpasser", "blackhole", "{", ip, "}"});
}

void GlobalRegistry::startHotHealingWatcher() {
    int fd = inotify_init1(IN_NONBLOCK | IN_CLOEXEC);
    if (fd < 0) return;
    inotify_add_watch(fd, ".", IN_DELETE | IN_MODIFY);
    struct pollfd pfd = {fd, POLLIN, 0};
    char buffer[4096];
    while (running_.load()) {
        if (poll(&pfd, 1, 1000) > 0 && (pfd.revents & POLLIN)) {
            if (read(fd, buffer, sizeof(buffer)) > 0) ensureConfigIntegrity();
        }
    }
    close(fd);
}

void GlobalRegistry::ensureConfigIntegrity() {
    std::error_code ec;
    if (fs::exists(Config::GOLDEN_CONF, ec) && !fs::exists(Config::CORE_CONF, ec)) {
        if (unlikely(!fs::copy_file(Config::GOLDEN_CONF, Config::CORE_CONF, fs::copy_options::overwrite_existing, ec))) {
            LOG_SYSERR << "Healing failed: " << ec.message();
        } else {
            LOG_INFO << "✨ Healing successful: core.conf restored.";
        }
    }
}
