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
  <view class="page olive-sheet with-nav mine-page">
    <view class="panel row profile-card">
      <view class="avatar"><AppIcon name="user" :size="58" /></view>
      <view class="grow">
        <view class="nickname">{{ auth.user?.nickname || roleName }}</view>
        <view class="tag identity-tag">{{ roleName }}</view>
        <view v-if="auth.user?.username" class="tiny profile-detail">{{ auth.user.username }}</view>
      </view>
    </view>

    <view v-if="!isUser" class="card-title section">管理账号</view>
    <view class="panel menu-list">
      <button class="menu" hover-class="menu-pressed" @tap="go('/subpackages/common/profile')">
        <view class="grow">
          <view>{{ isUser ? "个人资料" : "账号信息" }}</view>
          <view class="menu-description">修改昵称、年龄和性别</view>
        </view>
        <text class="chevron" aria-hidden="true">›</text>
      </button>
      <button v-if="!isUser" class="menu" hover-class="menu-pressed" @tap="go('/subpackages/common/activity')">
        <view class="grow">
          <view>我的操作记录</view>
          <view class="menu-description">查看{{ auth.user?.role === "knowledge_admin" ? "知识管理" : "运维" }}操作记录</view>
        </view>
        <text class="chevron" aria-hidden="true">›</text>
      </button>
      <button class="menu" hover-class="menu-pressed" @tap="go('/subpackages/common/security')">
        <view class="grow">
          <view>登录安全</view>
          <view class="menu-description">管理登录密码</view>
        </view>
        <text class="chevron" aria-hidden="true">›</text>
      </button>
      <button class="menu" hover-class="menu-pressed" @tap="go('/subpackages/common/help')">
        <view class="grow">
          <view>使用帮助</view>
          <view class="menu-description">拍摄方法与报告说明</view>
        </view>
        <text class="chevron" aria-hidden="true">›</text>
      </button>
    </view>
    <button class="outline logout" @tap="logout">退出登录</button>
    <RoleNav active="mine" />
  </view>
</template>

<style scoped>
.profile-card { gap: 24rpx; padding: 30rpx 24rpx; margin-bottom: 20rpx; border: 0; background: var(--tint); }
.profile-card .avatar { width: 112rpx; height: 112rpx; }
.profile-card .avatar :deep(.app-icon) { width: 58rpx !important; height: 58rpx !important; }
.nickname { font-size: 32rpx; font-weight: 600; overflow-wrap: anywhere; line-height: 1.4; }
.identity-tag { font-size: var(--font-caption); margin-top: 4rpx; padding: 0; color: var(--primary); background: transparent; }
.profile-detail { margin-top: 4rpx; color: var(--secondary-ink); overflow-wrap: anywhere; }
.menu-list { padding: 0 24rpx; border: 0; border-radius: 20rpx; }
.menu { width: 100%; min-height: 108rpx; background: var(--surface); color: var(--ink); padding: 18rpx 0; text-align: left; border: 0; border-radius: 0; line-height: 1.45; }
.menu::after { border: 0; }
.menu.menu-pressed { opacity: 0.72; }
.menu-list .menu + .menu { border-top: 1rpx solid var(--border); }
.menu .grow { font-size: var(--font-body); font-weight: 600; }
.menu-description { font-size: var(--font-secondary); color: var(--secondary-ink); margin-top: 5rpx; font-weight: 400; }
.menu .chevron { color: var(--accent); font-size: 36rpx; }
.logout { margin-top: 14rpx; border-color: var(--border); background: transparent; }
</style>
