<script setup lang="ts">
import { computed } from "vue";
import { onShow } from "@dcloudio/uni-app";
import { useAuth, requireAuth } from "@/stores/auth";
import { toastError, confirmAction } from "@/utils/request";
import AppIcon from "@/components/AppIcon.vue";
import RoleNav from "@/components/RoleNav.vue";
const auth = useAuth(),
  isUser = computed(() => auth.user?.role === "user");
const roleName = computed(() =>
  auth.user?.role === "knowledge_admin"
    ? "知识库管理员"
    : auth.user?.role === "ops_admin"
      ? "运维管理员"
      : "健康体验者",
);
onShow(async () => {
  if (requireAuth()) {
    try {
      await auth.refresh();
    } catch (e) {
      toastError(e);
    }
  }
});
function go(url: string) {
  uni.navigateTo({ url });
}
async function logout() {
  if (await confirmAction("退出当前账号？")) {
    try {
      await auth.logout();
    } catch (e) {
      toastError(e);
    }
  }
}
</script>
<template>
  <view class="page with-nav"
    ><view class="panel row profile-card"
      ><view class="avatar"><AppIcon name="user" :size="80" /></view
      ><view class="grow"
        ><view class="title">{{ auth.user?.nickname || roleName }}</view
        ><view class="tag">{{ roleName }}</view
        ><view class="muted small spaced">{{
          isUser ? "记录与回顾每次分析" : "账号：" + auth.user?.username
        }}</view></view
      ></view
    >
    <view v-if="!isUser" class="title section">管理账号</view
    ><view class="panel"
      ><view v-if="isUser" class="menu" @tap="go('/subpackages/user/history')"
        ><AppIcon name="clock" :size="52" /><view class="grow"
          ><view class="title">历史记录</view
          ><view class="muted small">查看已归档的分析报告</view></view
        ><text class="chevron">›</text></view
      ><view class="menu" @tap="go('/subpackages/common/profile')"
        ><AppIcon name="user" :size="52" /><view class="grow"
          ><view class="subtitle">{{ isUser ? "个人资料" : "账号信息" }}</view
          ><view v-if="!isUser" class="muted small"
            >查看与编辑个人资料</view
          ></view
        ><text class="chevron">›</text></view
      ><view
        v-if="!isUser"
        class="menu"
        @tap="go('/subpackages/common/activity')"
        ><AppIcon name="document" :size="52" /><view class="grow"
          ><view class="subtitle">我的操作记录</view
          ><view class="muted small"
            >查看{{
              auth.user?.role === "knowledge_admin" ? "知识管理" : "运维"
            }}操作记录</view
          ></view
        ><text class="chevron">›</text></view
      ></view
    >
    <view class="panel"
      ><view class="menu" @tap="go('/subpackages/common/security')"
        ><AppIcon name="lock" :size="52" /><view class="grow subtitle"
          >登录安全</view
        ><text class="chevron">›</text></view
      ><view class="menu" @tap="go('/subpackages/common/help')"
        ><AppIcon name="help" :size="52" /><view class="grow subtitle"
          >使用帮助</view
        ><text class="chevron">›</text></view
      ></view
    ><button class="outline spaced" @tap="logout">退出登录</button
    ><view class="footer-mark"
      ><image src="/static/branch.png" mode="aspectFit" /><view
        >舌象智能分析系统</view
      ></view
    ><RoleNav active="mine"
  /></view>
</template>
<style scoped>
.profile-card {
  padding: 32rpx 25rpx;
  margin-top: 15rpx;
  gap: 24rpx;
}
.menu:first-child {
  padding-top: 8rpx;
}
.menu:last-child {
  padding-bottom: 8rpx;
}
</style>
