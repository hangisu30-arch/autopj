<%@ page contentType="text/html; charset=UTF-8" pageEncoding="UTF-8"%>
<%@ taglib prefix="c" uri="http://java.sun.com/jsp/jstl/core"%>
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>TbMember 등록/수정</title>
</head>
<body>
<%@ include file="/WEB-INF/views/common/header.jsp" %>
<%@ include file="/WEB-INF/views/common/leftNav.jsp" %>
<section class="page-shell autopj-form-page">
  <div class="autopj-form-hero page-card">
    <div>
      <p class="autopj-eyebrow">TbMember</p>
      <h2 class="autopj-form-title">TbMember 등록/수정</h2>
    </div>
    <div class="autopj-form-hero__meta">
    </div>
  </div>
  <form class="autopj-form-card form-card" action="<c:url value='/tbMember/save.do'/>" method="post">
      <input type="hidden" name="_originalMemberId" value="<c:out value='${item.memberId}'/>"/>
    <div class="autopj-form-section-header">
      <div>
        <h3 class="autopj-section-title">기본 정보</h3>
      </div>
    </div>
    <div class="autopj-form-grid">
      <label class="autopj-field">
        <span class="autopj-field__label">Member Id</span>
        <input type="text" name="memberId" class="form-control" value="<c:out value='${item.memberId}'/>"/>
      </label>
      <script>document.addEventListener('DOMContentLoaded', function(){ var el = document.querySelector('input[name="memberId"]'); if (!el) return; var v = (el.value || '').trim(); if (v) { el.setAttribute('readonly', 'readonly'); el.setAttribute('data-autopj-id-lock', 'true'); } else { el.removeAttribute('readonly'); } });</script>
      <label class="autopj-field">
        <span class="autopj-field__label">승인 여부</span>
        <span class="autopj-field__hint">승인 상태를 선택합니다.</span>
        <select name="approvalStatus" class="form-control">
          <option value="PENDING" <c:if test="${empty item or item.approvalStatus == 'PENDING' || empty item.approvalStatus}">selected</c:if>>대기</option>
          <option value="APPROVED" <c:if test="${item.approvalStatus == 'APPROVED' || item.approvalStatus == 'Y'}">selected</c:if>>승인</option>
          <option value="REJECTED" <c:if test="${item.approvalStatus == 'REJECTED' || item.approvalStatus == 'N'}">selected</c:if>>반려</option>
        </select>
      </label>
      <label class="autopj-field">
        <span class="autopj-field__label">Reg Dt</span>
        <input type="date" name="regDt" class="form-control" value="<c:out value='${item.regDt}'/>" data-autopj-temporal="date" data-autopj-raw-value="<c:out value='${item.regDt}'/>"/>
      </label>
    </div>
    <div class="autopj-form-actions">
      <button type="submit">저장</button>
      <c:if test="${not empty item and not empty item.memberId}">
        <button type="submit" formaction="<c:url value='/tbMember/delete.do'/>" formmethod="post" onclick="return confirm('삭제하시겠습니까?');">삭제</button>
      </c:if>
      <a class="btn btn-secondary" href="<c:url value='/tbMember/list.do'/>">취소</a>
    </div>
  </form>
</section>
</body>
</html>
