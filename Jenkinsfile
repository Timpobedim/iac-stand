// Пайплайн стенда. Каждый шаг — цель Makefile: то же самое разработчик запускает у себя
// через docker compose run --rm tools <цель>, без «работает только в Jenkins».
pipeline {
    agent any

    options {
        timestamps()
        disableConcurrentBuilds()          // состояние Terraform и стенд — одни на всех
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '20'))
    }

    parameters {
        booleanParam(name: 'BAD_RELEASE', defaultValue: false,
                     description: 'Учебная авария: релиз с неверным паролем базы должен откатиться')
    }

    environment {
        VERSION = "${env.BUILD_NUMBER}"
    }

    stages {
        stage('Проверки') {
            steps {
                sh 'make check'
            }
        }

        stage('Образ') {
            steps {
                sh 'make build VERSION=$VERSION'
            }
        }

        stage('Инфраструктура') {
            steps {
                withCredentials([string(credentialsId: 'tf-pg-conn', variable: 'PG_CONN_STR')]) {
                    sh 'make infra'
                }
            }
        }

        stage('Выкат') {
            steps {
                withCredentials([string(credentialsId: 'tf-pg-conn', variable: 'PG_CONN_STR')]) {
                    sh 'make deploy VERSION=$VERSION BAD=$BAD_RELEASE'
                }
            }
        }

        stage('Проверка стенда') {
            steps {
                withCredentials([string(credentialsId: 'tf-pg-conn', variable: 'PG_CONN_STR')]) {
                    sh 'make test'
                }
            }
            post {
                failure {
                    // Ansible уже откатывает экземпляры, если новая версия не поднялась. Здесь — случай,
                    // когда выкат прошёл, а проверка стенда упала: вернуть последнюю успешную сборку.
                    script {
                        def good = currentBuild.previousSuccessfulBuild?.number
                        if (good) {
                            withCredentials([string(credentialsId: 'tf-pg-conn', variable: 'PG_CONN_STR')]) {
                                sh "make deploy VERSION=${good}"
                            }
                        }
                    }
                }
            }
        }
    }

    post {
        always {
            junit allowEmptyResults: true, testResults: 'reports/*.xml'
        }
    }
}
