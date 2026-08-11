import { apiGet, apiPost } from './base'

const BASE_URL = '/api/resource-submissions'

export const resourceSubmissionApi = {
  getMine() {
    return apiGet(`${BASE_URL}/mine`)
  },
  getReviewQueue(status = 'pending') {
    return apiGet(`${BASE_URL}/review-queue?status=${encodeURIComponent(status)}`)
  },
  approve(submissionId, comment = '') {
    return apiPost(`${BASE_URL}/${encodeURIComponent(submissionId)}/approve`, { comment })
  },
  reject(submissionId, comment) {
    return apiPost(`${BASE_URL}/${encodeURIComponent(submissionId)}/reject`, { comment })
  }
}
