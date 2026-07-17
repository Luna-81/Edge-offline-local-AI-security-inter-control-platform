#define likely(x)   __builtin_expect(!!(x), 1)
#define unlikely(x) __builtin_expect(!!(x), 0)

#include <linux/bpf.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <linux/in.h>
#include <bpf/bpf_helpers.h>
#include <bpf/bpf_endian.h>

// ================================
// 🔥 Map 定义
// ================================

// --- 1. 全局配置 ---
struct config_t {
    __u32 syn_threshold;
};

struct {
    __uint(type, BPF_MAP_TYPE_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct config_t);
} global_config SEC(".maps");

// --- 2. 允许端口 ---
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 1024);
    __type(key, __u16);
    __type(value, __u8);
} allowed_ports SEC(".maps");

// --- 3. 黑名单 ---
struct blacklist_val {
    __u64 expire;
    __u32 reason;
};

struct {
    __uint(type, BPF_MAP_TYPE_LRU_HASH);
    __uint(max_entries, 100000);
    __type(key, __u32);
    __type(value, struct blacklist_val);
} blacklist_map SEC(".maps");

// --- 4. 白名单 ---
struct {
    __uint(type, BPF_MAP_TYPE_HASH);
    __uint(max_entries, 256);
    __type(key, __u32);
    __type(value, __u8);
} whitelist_map SEC(".maps");

// --- 5. SYN 速率限制 ---
struct rate_limit_val {
    __u64 last_ts;
    __u32 count;
};

struct {
    __uint(type, BPF_MAP_TYPE_LRU_HASH);
    __uint(max_entries, 50000);
    __type(key, __u32);
    __type(value, struct rate_limit_val);
} rate_limit_map SEC(".maps");


// ================================
// 🔥 动态速率检查
// ================================
static __always_inline int check_rate_limit(__u32 ip, __u64 now)
{
    struct rate_limit_val *val;
    struct config_t *conf;
    __u32 zero = 0;
    __u32 threshold = 200;

    conf = bpf_map_lookup_elem(&global_config, &zero);
    if (conf)
        threshold = conf->syn_threshold;

    val = bpf_map_lookup_elem(&rate_limit_map, &ip);

    if (!val) {
        struct rate_limit_val new = {
            .last_ts = now,
            .count = 1,
        };
        bpf_map_update_elem(&rate_limit_map, &ip, &new, BPF_ANY);
        return 0;
    }

    // 1 秒窗口
    if (now - val->last_ts > 1000000000ULL) {
        val->last_ts = now;
        val->count = 1;
        return 0;
    }

    val->count++;
    return val->count > threshold;
}


// ================================
// 🔥 主 XDP 程序（唯一入口）
// ================================
SEC("xdp")
int xdp_filter_main(struct xdp_md *ctx)
{
    void *data_end = (void *)(long)ctx->data_end;
    void *data = (void *)(long)ctx->data;

    // ========================
    // L2: Ethernet
    // ========================
    struct ethhdr *eth = data;
    if (unlikely((void *)(eth + 1) > data_end))
        return XDP_PASS;

    if (eth->h_proto != bpf_htons(ETH_P_IP))
        return XDP_PASS;

    // ========================
    // L3: IPv4
    // ========================
    struct iphdr *iph = (void *)(eth + 1);
    if (unlikely((void *)(iph + 1) > data_end))
        return XDP_PASS;

    if (iph->protocol != IPPROTO_TCP)
        return XDP_PASS;

    __u32 src_ip = iph->saddr;

    // ========================
    // 🔥 1. 白名单（最高优先级）
    // ========================
    if (bpf_map_lookup_elem(&whitelist_map, &src_ip))
        return XDP_PASS;

    // ========================
    // 🔥 2. 黑名单（带 TTL）
    // ========================
    struct blacklist_val *blk;
    blk = bpf_map_lookup_elem(&blacklist_map, &src_ip);

    if (blk) {
        if (blk->expire > bpf_ktime_get_ns())
            return XDP_DROP;
    }

    // ========================
    // L4: TCP
    // ========================
    __u32 ihl_len = iph->ihl << 2;
    if (unlikely(ihl_len < sizeof(*iph)))
        return XDP_PASS;

    struct tcphdr *tcp = (void *)((__u8 *)iph + ihl_len);
    if (unlikely((void *)(tcp + 1) > data_end))
        return XDP_PASS;

    __u16 dest_port = bpf_ntohs(tcp->dest);

    // ========================
    // 🔥 3. 端口过滤（核心）
    // ========================
    if (!bpf_map_lookup_elem(&allowed_ports, &dest_port)) {
        return XDP_DROP;
    }

    // ========================
    // 🔥 4. SYN Flood 防护
    // ========================
    if (tcp->syn && !tcp->ack) {
        __u64 now = bpf_ktime_get_ns();

        if (check_rate_limit(src_ip, now)) {
            struct blacklist_val new = {
                .expire = now + 60ULL * 1000000000ULL,
                .reason = 1,
            };

            bpf_map_update_elem(&blacklist_map, &src_ip, &new, BPF_ANY);
            return XDP_DROP;
        }
    }

    return XDP_PASS;
}

char LICENSE[] SEC("license") = "GPL";
