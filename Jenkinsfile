pipeline {
  agent any
  stages {
    stage('Build') {
      steps {
        sh 'docker build -t aiwarssoc/submission-runner:latest .'
      }
    }

    stage('Push') {
      steps {
        sh 'docker push aiwarssoc/submission-runner:latest'
      }
    }

  }
}